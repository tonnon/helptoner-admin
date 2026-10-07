import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.cadastros.models import Produto
from apps.pedidos.models import ContadorPedido, Pedido
from apps.pedidos.services import cancelar_pedido, criar_rascunho
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    criar_usuario,
    montar_pedido_confirmado,
    montar_rascunho,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def rascunho(vendedor):
    return criar_rascunho(vendedor)


def htmx_post(client, url, dados):
    return client.post(
        url, dados, headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/"}
    )


def test_novo_pedido_abre_o_editor(client_vendedor):
    r = client_vendedor.post("/pedidos/novo/")
    ped = Pedido.objects.get()
    assert r["Location"] == f"/pedidos/{ped.pk}/editar/"
    html = client_vendedor.get(r["Location"]).content.decode()
    assert "Novo pedido" in html and "Rascunho" in html and "Confirmar pedido" in html


def test_adicionar_item_atualiza_itens_e_resumo(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(preco="189.90"), 12)
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"produto_id": prod.pk, "quantidade": "2"},
    ).content.decode()
    assert (
        "Toner HP 85A Preto" in html
        and 'id="resumo"' in html
        and "hx-swap-oob" in html
        and "R$ 379,80" in html
    )


@pytest.mark.parametrize(
    ("qtd", "erro"),
    [
        ("abc", "Informe uma quantidade inteira maior que zero."),
        ("1,5", "Informe uma quantidade inteira maior que zero."),
        ("0", "Informe uma quantidade inteira maior que zero."),
        ("-1", "Informe uma quantidade inteira maior que zero."),
        ("", "Informe uma quantidade inteira maior que zero."),
        ("10000", "Quantidade máxima por item: 9.999."),
    ],
)
def test_quantidade_invalida_nao_grava(client_vendedor, rascunho, qtd, erro):
    prod = com_estoque(criar_produto(), 12)
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"produto_id": prod.pk, "quantidade": qtd},
    ).content.decode()
    assert erro in html and not rascunho.itens.exists()


def test_estoque_insuficiente_mostra_quanto_ainda_cabe(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(), 12)
    htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"produto_id": prod.pk, "quantidade": "10"},
    )
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"produto_id": prod.pk, "quantidade": "3"},
    ).content.decode()
    assert "dá para adicionar mais 2" in html


def test_desconto_com_virgula_e_texto_invalido(client_vendedor, rascunho):
    htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/desconto/",
        {"tipo": "percentual", "valor": "10,5"},
    )
    rascunho.refresh_from_db()
    assert rascunho.desconto_informado == Decimal("10.50")
    html = htmx_post(
        client_vendedor, f"/pedidos/{rascunho.pk}/desconto/", {"tipo": "percentual", "valor": "abc"}
    ).content.decode()
    assert "Informe um número. Ex.: 10 ou 10,5" in html


def test_desconto_maior_que_o_subtotal_depois_de_remover_item(client_vendedor, vendedor):  # RF 4
    a = com_estoque(criar_produto("CE285A", preco="189.90"), 5)
    b = com_estoque(criar_produto("TN-1060", preco="89.90"), 5)
    ped = montar_rascunho(
        vendedor, cliente=criar_cliente(), itens=[(a, 1), (b, 1)], desconto=("reais", "100")
    )
    html = htmx_post(
        client_vendedor, f"/pedidos/{ped.pk}/itens/{ped.itens.get(produto=a).pk}/remover/", {}
    ).content.decode()
    assert "O desconto não pode passar do subtotal." in html and "R$ 89,90" in html
    html = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {}).content.decode()
    assert "O desconto não pode passar do subtotal." in html
    ped.refresh_from_db()
    assert ped.status == "rascunho"


def test_confirmar_vai_para_o_detalhe_com_aviso(client_vendedor, vendedor):
    ped = montar_rascunho(
        vendedor, cliente=criar_cliente(), itens=[(com_estoque(criar_produto(), 5), 1)]
    )
    r = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {})
    assert r["HX-Redirect"] == f"/pedidos/{ped.pk}/"
    assert "Pedido nº 1 confirmado" in client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()


def test_confirmar_com_preco_alterado_mostra_o_que_mudou(client_vendedor, vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 5)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1)])
    Produto.objects.filter(pk=prod.pk).update(preco=Decimal("189.90"))
    html = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {}).content.decode()
    assert "CE285A: de R$ 179,90 para R$ 189,90" in html and "confirme de novo" in html


def test_rascunho_de_outra_pessoa(client_vendedor):
    ped = criar_rascunho(criar_usuario(email="outro@helptoner.com.br"))
    assert client_vendedor.get(f"/pedidos/{ped.pk}/editar/")["Location"] == f"/pedidos/{ped.pk}/"
    assert (
        htmx_post(client_vendedor, f"/pedidos/{ped.pk}/observacoes/", {"texto": "x"}).status_code
        == 403
    )


def test_pedido_confirmado_nao_abre_no_editor(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert client_vendedor.get(f"/pedidos/{ped.pk}/editar/")["Location"] == f"/pedidos/{ped.pk}/"


def test_sessao_expirada_no_rascunho_volta_ao_pedido(client, vendedor):  # Review Focus 1
    ped = criar_rascunho(vendedor)
    r = client.post(
        f"/pedidos/{ped.pk}/itens/",
        {"produto_id": "1", "quantidade": "1"},
        headers={
            "HX-Request": "true",
            "HX-Current-URL": f"http://testserver/pedidos/{ped.pk}/editar/",
        },
    )
    assert r["HX-Redirect"] == f"/contas/login/?next=/pedidos/{ped.pk}/editar/"


def test_repetir_abre_o_novo_rascunho(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    r = client_vendedor.post(f"/pedidos/{ped.pk}/repetir/")
    assert r["Location"] == f"/pedidos/{Pedido.objects.latest('pk').pk}/editar/"


# Além do plano: a tela inteira, os outros botões e os casos de erro.


def test_editor_mostra_o_rascunho(client_vendedor, vendedor):
    cli = criar_cliente("Papelaria Central Ltda", documento="11222333000181", cidade="Campinas")
    ped = montar_rascunho(
        vendedor, cliente=cli, itens=[(com_estoque(criar_produto(preco="189.90"), 12), 2)]
    )
    html = client_vendedor.get(f"/pedidos/{ped.pk}/editar/").content.decode()
    for trecho in [
        "Papelaria Central Ltda",
        "11.222.333/0001-81",
        "Toner HP 85A Preto",
        'data-valor-centavos="37980"',
        'id="barra-celular"',
        'placeholder="Buscar cliente por nome, CPF ou CNPJ"',
        'placeholder="Buscar produto por código ou nome"',
        '<label for="quantidade"',
        '<label class="rotulo" for="desconto">Desconto</label>',
        "Estoque e total conferidos ao confirmar",
        "js/sugestoes.js",
    ]:
        assert trecho in html, trecho
    assert "hx-swap-oob" not in html


def test_selo_mostra_a_hora_de_brasilia(client_vendedor, rascunho):
    Pedido.objects.filter(pk=rascunho.pk).update(
        atualizado_em=datetime(2026, 10, 6, 17, 5, tzinfo=UTC)
    )
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/editar/").content.decode()
    assert "Rascunho · salvo às 14:05" in html


def test_foco_no_cliente_e_depois_no_produto(client_vendedor, vendedor, rascunho):
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/editar/").content.decode()
    assert html.count("autofocus") == 1 and 'id="busca-cliente"' in html.split("autofocus")[0]
    ped = montar_rascunho(vendedor, cliente=criar_cliente())
    html = client_vendedor.get(f"/pedidos/{ped.pk}/editar/").content.decode()
    assert html.count("autofocus") == 1 and 'id="busca-produto"' in html.split("autofocus")[0]


def test_incluir_item_limpa_o_formulario_e_destaca_a_linha(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(), 12)
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"q": "CE285A · Toner HP 85A Preto", "produto_id": prod.pk, "quantidade": "2"},
    ).content.decode()
    item = rascunho.itens.get()
    assert f'<tr id="item-{item.pk}" class="nova">' in html
    assert '<form id="form-item"' in html and 'id="produto-id" name="produto_id" value=""' in html
    assert "CE285A · Toner HP 85A Preto" not in html  # o campo de busca volta vazio
    assert 'id="busca-produto"' in html.split("autofocus")[0]


def test_erro_no_item_mantem_o_produto_escolhido(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(preco="189.90"), 12)
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"q": "CE285A · Toner HP 85A Preto", "produto_id": prod.pk, "quantidade": "13"},
    ).content.decode()
    assert "Estoque insuficiente: 12 em estoque." in html
    assert 'value="CE285A · Toner HP 85A Preto"' in html and f'value="{prod.pk}"' in html
    assert 'value="13"' in html and "campo campo-quantidade campo-invalido" in html
    assert "R$ 189,90</b> cada · <b>12</b> em estoque" in html


@pytest.mark.parametrize("produto_id", ["", "abc", "0", "999999", "99999999999999999999"])
def test_produto_invalido_pede_para_escolher_na_lista(client_vendedor, rascunho, produto_id):
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"produto_id": produto_id, "quantidade": "1"},
    ).content.decode()
    assert "Escolha um produto na lista de sugestões." in html and not rascunho.itens.exists()
    assert "campo campo-invalido" in html  # o campo de busca do produto


def test_quantidade_com_muitos_digitos(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(), 12)
    for qtd in ["9" * 5000, "0" * 20 + "5"]:
        htmx_post(
            client_vendedor,
            f"/pedidos/{rascunho.pk}/itens/",
            {"produto_id": prod.pk, "quantidade": qtd},
        )
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{rascunho.pk}/itens/",
        {"produto_id": prod.pk, "quantidade": "9" * 5000},
    ).content.decode()
    assert "Quantidade máxima por item: 9.999." in html
    assert rascunho.itens.get().quantidade == 5


def test_mais_e_menos(client_vendedor, vendedor):
    ped = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 3), 2)])
    item = ped.itens.get()
    url = f"/pedidos/{ped.pk}/itens/{item.pk}/quantidade/"

    def quantidade():
        item.refresh_from_db()
        return item.quantidade

    htmx_post(client_vendedor, url, {"acao": "mais"})
    assert quantidade() == 3
    html = htmx_post(client_vendedor, url, {"acao": "mais"}).content.decode()
    assert "Estoque insuficiente para CE285A: 3 em estoque." in html and quantidade() == 3
    htmx_post(client_vendedor, url, {"acao": "menos"})
    assert quantidade() == 2
    htmx_post(client_vendedor, url, {"quantidade": "1"})
    assert quantidade() == 1
    html = htmx_post(client_vendedor, url, {"quantidade": "x"}).content.decode()
    assert "Informe uma quantidade inteira maior que zero." in html and quantidade() == 1
    html = htmx_post(client_vendedor, url, {"acao": "menos"}).content.decode()
    assert "Informe uma quantidade inteira maior que zero." in html and quantidade() == 1


def test_menos_fica_desligado_na_quantidade_1(client_vendedor, vendedor):
    ped = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 3), 1)])
    html = client_vendedor.get(f"/pedidos/{ped.pk}/editar/").content.decode()
    assert 'aria-label="Diminuir CE285A" disabled' in html


def test_item_que_ja_saiu_do_pedido(client_vendedor, vendedor):
    ped = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 3), 1)])
    item = ped.itens.get()
    htmx_post(client_vendedor, f"/pedidos/{ped.pk}/itens/{item.pk}/remover/", {})
    html = htmx_post(
        client_vendedor, f"/pedidos/{ped.pk}/itens/{item.pk}/quantidade/", {"acao": "mais"}
    ).content.decode()
    assert "Este item não está mais no pedido." in html
    assert "Nenhum item ainda. Busque um produto pelo código ou nome." in html


def test_remover_tem_a_animacao_de_saida(client_vendedor, vendedor):
    ped = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 3), 1)])
    html = client_vendedor.get(f"/pedidos/{ped.pk}/editar/").content.decode()
    assert 'hx-swap="outerHTML swap:280ms" data-remover-linha' in html


def test_linha_com_problema_mostra_o_aviso(client_vendedor, vendedor):
    prod = com_estoque(criar_produto(), 3)
    ped = montar_rascunho(vendedor, itens=[(prod, 3)])
    Produto.objects.filter(pk=prod.pk).update(ativo=False)
    html = client_vendedor.get(f"/pedidos/{ped.pk}/editar/").content.decode()
    assert "O produto CE285A foi inativado. Remova-o do pedido." in html


def test_escolher_cliente(client_vendedor, rascunho):
    cli = criar_cliente("Papelaria Central Ltda")
    r = htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/cliente/", {"cliente_id": cli.pk})
    html = r.content.decode()
    rascunho.refresh_from_db()
    assert rascunho.cliente == cli
    assert '<div id="cliente" data-cliente hx-swap-oob="true">' in html
    assert "Papelaria Central Ltda" in html and "Trocar" in html
    # O foco vai para a busca de produto sem redesenhar o formulário do item, onde a pessoa
    # pode já estar digitando (o teste no navegador da Tarefa 20 digita logo depois do clique).
    assert json.loads(r["HX-Trigger-After-Settle"]) == {"focar": "busca-produto"}
    assert 'id="form-item"' not in html


def test_cliente_inativo_ou_invalido_nao_e_escolhido(client_vendedor, rascunho):
    inativo = criar_cliente("Papelaria Antiga", ativo=False)
    html = htmx_post(
        client_vendedor, f"/pedidos/{rascunho.pk}/cliente/", {"cliente_id": inativo.pk}
    ).content.decode()
    assert "Este cliente está inativo. Escolha outro cliente." in html
    for valor in ["", "abc", "999999"]:
        html = htmx_post(
            client_vendedor, f"/pedidos/{rascunho.pk}/cliente/", {"cliente_id": valor}
        ).content.decode()
        assert "Escolha um cliente na lista de sugestões." in html, valor
    rascunho.refresh_from_db()
    assert rascunho.cliente is None


def test_desconto_vazio_vale_zero_e_limites(client_vendedor, rascunho):
    url = f"/pedidos/{rascunho.pk}/desconto/"
    htmx_post(client_vendedor, url, {"tipo": "reais", "valor": "15"})
    html = htmx_post(client_vendedor, url, {"tipo": "reais", "valor": ""}).content.decode()
    rascunho.refresh_from_db()
    assert (rascunho.desconto_tipo, rascunho.desconto_informado) == ("reais", Decimal("0"))
    assert '<div id="campo-desconto" class="campo" hx-swap-oob="true">' in html
    html = htmx_post(client_vendedor, url, {"tipo": "percentual", "valor": "150"}).content.decode()
    assert "O desconto não pode passar de 100%." in html and 'value="150"' in html
    assert "campo campo-invalido" in html
    html = htmx_post(client_vendedor, url, {"tipo": "outro", "valor": "1"}).content.decode()
    assert "Tipo de desconto inválido." in html
    rascunho.refresh_from_db()
    assert rascunho.desconto_tipo == "reais"


def test_observacoes(client_vendedor, rascunho):
    url = f"/pedidos/{rascunho.pk}/observacoes/"
    htmx_post(client_vendedor, url, {"texto": "  Entregar na portaria  "})
    rascunho.refresh_from_db()
    assert rascunho.observacoes == "Entregar na portaria"
    r = htmx_post(client_vendedor, url, {"texto": "x" * 1001})
    assert json.loads(r["HX-Trigger"]) == {
        "aviso": {"texto": "As observações podem ter até 1.000 caracteres.", "tipo": "erro"}
    }
    rascunho.refresh_from_db()
    assert rascunho.observacoes == "Entregar na portaria"


def test_observacoes_com_caractere_nulo(client_vendedor, rascunho):  # Ruling R23
    r = htmx_post(
        client_vendedor, f"/pedidos/{rascunho.pk}/observacoes/", {"texto": "Entregar\x00 já"}
    )
    rascunho.refresh_from_db()
    assert r.status_code == 200 and rascunho.observacoes == "Entregar já"


def _rascunho_pronto(vendedor, preco="189.90", quantidade=2):
    return montar_rascunho(
        vendedor,
        cliente=criar_cliente(),
        itens=[(com_estoque(criar_produto(preco=preco), 5), quantidade)],
    )


def test_confirmar_grava_antes_o_desconto_e_as_observacoes_da_tela(
    client_vendedor, vendedor
):  # Ruling R24
    ped = _rascunho_pronto(vendedor)
    r = htmx_post(
        client_vendedor,
        f"/pedidos/{ped.pk}/confirmar/",
        {"tipo": "percentual", "valor": "10", "texto": "Entregar na portaria"},
    )
    assert r["HX-Redirect"] == f"/pedidos/{ped.pk}/"
    ped.refresh_from_db()
    assert (ped.status, ped.desconto_tipo, ped.desconto_informado, ped.total) == (
        "confirmado",
        "percentual",
        Decimal("10.00"),
        Decimal("341.82"),
    )
    assert ped.observacoes == "Entregar na portaria"


@pytest.mark.parametrize(
    ("tipo", "valor", "erro"),
    [
        ("percentual", "7.5", "Informe um número. Ex.: 10 ou 10,5"),
        ("reais", "R$ 10", "Informe um número. Ex.: 10 ou 10,5"),
        ("percentual", "150", "O desconto não pode passar de 100%."),
        ("outro", "10", "Tipo de desconto inválido."),
    ],
)
def test_confirmar_com_desconto_invalido_na_tela_nao_confirma(
    client_vendedor, vendedor, tipo, valor, erro
):  # Ruling R24
    ped = _rascunho_pronto(vendedor)
    html = htmx_post(
        client_vendedor,
        f"/pedidos/{ped.pk}/confirmar/",
        {"tipo": tipo, "valor": valor, "texto": "Entregar na portaria"},
    ).content.decode()
    assert erro in html and "campo campo-invalido" in html
    campo = html.split('<input id="desconto"')[1].split(">")[0]
    assert f'value="{valor}"' in campo and "autofocus" in campo  # o foco volta ao desconto
    ped.refresh_from_db()
    assert (ped.status, ped.desconto_informado) == ("rascunho", Decimal("0"))
    assert ContadorPedido.objects.get().ultimo_numero == 0  # nenhum número gasto
    assert ped.observacoes == "Entregar na portaria"  # o que vale é gravado


def test_botoes_de_confirmar_levam_o_desconto_e_as_observacoes(client_vendedor, rascunho):
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/editar/").content.decode()
    assert html.count('hx-include="#form-desconto, #observacoes"') == 2
    assert html.count('data-espera-mudancas data-confere-campo="desconto"') == 2


def test_confirmar_sem_cliente_mostra_os_motivos(client_vendedor, vendedor):
    ped = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    html = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {}).content.decode()
    assert "Escolha o cliente antes de confirmar." in html and 'role="alert"' in html
    ped.refresh_from_db()
    assert ped.status == "rascunho"


def test_acao_em_pedido_que_ja_nao_e_rascunho_volta_ao_detalhe(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    r = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/observacoes/", {"texto": "x"})
    assert r["HX-Redirect"] == f"/pedidos/{ped.pk}/"
    html = client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "O pedido nº 1 já foi confirmado e não pode mais ser editado." in html


def test_editar_explica_por_que_nao_abre(client_vendedor, administrador, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    cancelar_pedido(ped.pk, "Cliente desistiu", administrador)
    html = client_vendedor.get(f"/pedidos/{ped.pk}/editar/", follow=True).content.decode()
    assert "O pedido nº 1 foi cancelado e não pode ser editado." in html
    alheio = criar_rascunho(administrador)
    html = client_vendedor.get(f"/pedidos/{alheio.pk}/editar/", follow=True).content.decode()
    assert "Só quem criou o rascunho ou um administrador pode editá-lo." in html


def test_administrador_edita_rascunho_de_outra_pessoa(client_admin, rascunho):
    assert client_admin.get(f"/pedidos/{rascunho.pk}/editar/").status_code == 200
    r = htmx_post(client_admin, f"/pedidos/{rascunho.pk}/observacoes/", {"texto": "ok"})
    assert r.status_code == 200


def test_excluir_rascunho(client_vendedor, rascunho):
    r = client_vendedor.post(f"/pedidos/{rascunho.pk}/excluir/", follow=True)
    assert r.redirect_chain[0][0] == "/pedidos/"
    assert "Rascunho excluído." in r.content.decode()
    assert not Pedido.objects.filter(pk=rascunho.pk).exists()


def test_excluir_rascunho_de_outra_pessoa(client_vendedor):
    ped = criar_rascunho(criar_usuario(email="outro@helptoner.com.br"))
    assert client_vendedor.post(f"/pedidos/{ped.pk}/excluir/").status_code == 403
    assert Pedido.objects.filter(pk=ped.pk).exists()


def test_repetir_rascunho_nao_vale(client_vendedor, rascunho):
    r = client_vendedor.post(f"/pedidos/{rascunho.pk}/repetir/", follow=True)
    assert r.redirect_chain[0][0] == f"/pedidos/{rascunho.pk}/"
    assert "Só pedidos confirmados ou cancelados podem ser repetidos." in r.content.decode()


@pytest.mark.parametrize(
    "rota",
    [
        "novo/",
        "{pk}/cliente/",
        "{pk}/itens/",
        "{pk}/itens/{item}/quantidade/",
        "{pk}/itens/{item}/remover/",
        "{pk}/desconto/",
        "{pk}/observacoes/",
        "{pk}/confirmar/",
        "{pk}/excluir/",
        "{pk}/repetir/",
    ],
)
def test_rotas_que_mudam_so_aceitam_post(client_vendedor, vendedor, rota):
    ped = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    url = "/pedidos/" + rota.format(pk=ped.pk, item=ped.itens.get().pk)
    assert client_vendedor.get(url).status_code == 405
    ped.refresh_from_db()
    assert ped.itens.get().quantidade == 1


def test_detalhe_e_lista_ganham_os_botoes(client_vendedor, vendedor, administrador):
    html = client_vendedor.get("/pedidos/").content.decode()
    assert 'action="/pedidos/novo/"' in html and "+ Novo pedido" in html
    proprio = montar_rascunho(vendedor)
    html = client_vendedor.get(f"/pedidos/{proprio.pk}/").content.decode()
    assert "Continuar editando" in html and f'href="/pedidos/{proprio.pk}/editar/"' in html
    assert "Repetir pedido" not in html
    alheio = montar_rascunho(administrador)
    assert (
        "Continuar editando" not in client_vendedor.get(f"/pedidos/{alheio.pk}/").content.decode()
    )
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    html = client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "Repetir pedido" in html and f'action="/pedidos/{ped.pk}/repetir/"' in html
    assert "Continuar editando" not in html
