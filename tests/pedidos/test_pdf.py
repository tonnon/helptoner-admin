from io import BytesIO
from unittest.mock import Mock

import pytest
from pypdf import PdfReader

from apps.core.formatacao import data_hora_br
from apps.pedidos.pdf import gerar_pdf_pedido
from apps.pedidos.services import cancelar_pedido, criar_rascunho
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    montar_pedido_confirmado,
    texto_do_pdf,
)

pytestmark = pytest.mark.django_db


def test_pdf_tem_os_dados_e_aceita_acentos(vendedor):
    cli = criar_cliente("João & Cia — Comércio Ltda", documento="12ABC34501DE35", cidade="São José")
    ped = montar_pedido_confirmado(
        vendedor,
        cliente=cli,
        itens=[(com_estoque(criar_produto(preco="125.00"), 5, "60.00"), 2)],
        desconto=("percentual", "10"),
    )
    dados = gerar_pdf_pedido(ped)
    texto = texto_do_pdf(dados)
    assert dados.startswith(b"%PDF-")
    for trecho in [
        "Pedido nº 1",
        "João & Cia — Comércio Ltda",
        "12.ABC.345/01DE-35",
        "São José",
        "Toner HP 85A Preto",
        "R$ 250,00",
        "Desconto (10%)",
        "R$ 225,00",
        "Emitido por Carla",
    ]:
        assert trecho in texto
    assert "Custo" not in texto and "Lucro" not in texto


def test_pdf_traz_a_data_da_confirmacao_e_os_itens_em_colunas(vendedor):
    ped = montar_pedido_confirmado(
        vendedor, itens=[(com_estoque(criar_produto(preco="125.00"), 5), 2)]
    )
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    # O PDF usa o dia e a hora de Brasília, no formato da tela do pedido.
    assert f"Confirmado em {data_hora_br(ped.confirmado_em)}" in texto
    for coluna in ["Código", "Descrição", "Qtd.", "Unit.", "Total"]:
        assert coluna in texto
    assert "CE285A" in texto and "R$ 125,00" in texto


def test_pdf_traz_o_cliente_com_contato_e_endereco_completo(vendedor):
    cli = criar_cliente(
        "Papelaria Central Ltda",
        documento="11222333000181",
        telefone="(11) 3333-4444",
        email="compras@papelaria.com.br",
        cep="01234567",
        logradouro="Rua das Flores",
        numero="123",
        complemento="Sala 4",
        bairro="Centro",
        cidade="São Paulo",
        uf="SP",
    )
    ped = montar_pedido_confirmado(
        vendedor, cliente=cli, itens=[(com_estoque(criar_produto(), 5), 1)]
    )
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    for trecho in [
        "Papelaria Central Ltda",
        "CNPJ 11.222.333/0001-81",
        "Telefone (11) 3333-4444",
        "E-mail compras@papelaria.com.br",
        "Rua das Flores, 123 - Sala 4",
        "Centro - São Paulo/SP - CEP 01234-567",
    ]:
        assert trecho in texto


def test_pdf_de_pessoa_fisica_sem_contato_nem_endereco(vendedor):
    cli = criar_cliente("Maria da Silva", tipo="PF", documento="52998224725")
    ped = montar_pedido_confirmado(
        vendedor, cliente=cli, itens=[(com_estoque(criar_produto(), 5), 1)]
    )
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    assert "Maria da Silva" in texto and "CPF 529.982.247-25" in texto
    # O que o cadastro não tem não vira linha vazia nem "None".
    for ausente in ["CNPJ", "Telefone", "E-mail", "CEP", "None"]:
        assert ausente not in texto


@pytest.mark.parametrize(
    ("desconto", "rotulo", "valor"),
    [
        (("percentual", "10"), "Desconto (10%)", "− R$ 20,00"),
        (("percentual", "7.5"), "Desconto (7,50%)", "− R$ 15,00"),  # floatformat:"-2" da tela
        (("reais", "15"), "Desconto", "− R$ 15,00"),
    ],
)
def test_pdf_mostra_o_desconto_como_na_tela_do_pedido(vendedor, desconto, rotulo, valor):
    ped = montar_pedido_confirmado(
        vendedor,
        itens=[(com_estoque(criar_produto(preco="100.00"), 5), 2)],
        desconto=desconto,
    )
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    assert "Subtotal" in texto and "R$ 200,00" in texto
    assert rotulo in texto and valor in texto
    if desconto[0] == "reais":
        assert "Desconto (" not in texto


def test_pdf_sem_desconto_nao_tem_linha_de_desconto(vendedor):
    ped = montar_pedido_confirmado(
        vendedor, itens=[(com_estoque(criar_produto(preco="100.00"), 5), 2)]
    )
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    assert "Desconto" not in texto
    assert "Subtotal" in texto and "Total" in texto and "R$ 200,00" in texto


def test_pdf_mostra_as_observacoes_so_quando_existem(vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert "Observações" not in texto_do_pdf(gerar_pdf_pedido(ped))
    ped.observacoes = "Entregar na portaria, falar com a Dona Rita."
    ped.save(update_fields=["observacoes"])
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    assert "Observações" in texto and "Entregar na portaria, falar com a Dona Rita." in texto


def test_pdf_do_cancelado_vem_marcado(vendedor, administrador):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    ped = cancelar_pedido(ped.pk, "Cliente desistiu", administrador)
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    assert "CANCELADO" in texto and "Cliente desistiu" in texto
    assert f"CANCELADO em {data_hora_br(ped.cancelado_em)} por Lucas" in texto


def test_pdf_do_confirmado_nao_fala_em_cancelamento(vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert "CANCELADO" not in texto_do_pdf(gerar_pdf_pedido(ped)).upper()


def test_pdf_de_pedido_grande_quebra_pagina_e_fecha_os_totais_na_ultima(vendedor, administrador):
    itens = [
        (com_estoque(criar_produto(f"P{n:03d}", preco="10.00"), 5, por=administrador), 1)
        for n in range(1, 61)
    ]
    ped = montar_pedido_confirmado(vendedor, itens=itens, desconto=("reais", "10"))
    paginas = [pagina.extract_text() for pagina in PdfReader(BytesIO(gerar_pdf_pedido(ped))).pages]
    assert len(paginas) >= 2
    for numero, texto in enumerate(paginas, start=1):
        assert "Pedido nº 1" in texto and "Código" in texto  # cabeçalho e títulos das colunas
        assert f"Página {numero} de {len(paginas)}" in texto
    assert "P001" in paginas[0] and "P060" in paginas[-1]
    # Subtotal, desconto e total ficam juntos, no fim.
    ultima = paginas[-1]
    assert "R$ 600,00" in ultima and "− R$ 10,00" in ultima and "R$ 590,00" in ultima


# ---------- Rota de download ----------


def test_download_e_rascunho_sem_pdf(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    r = client_vendedor.get(f"/pedidos/{ped.pk}/pdf/")
    assert r["Content-Type"] == "application/pdf"
    assert r["Content-Disposition"] == 'attachment; filename="pedido-1.pdf"'
    assert r.content.startswith(b"%PDF-") and "Pedido nº 1" in texto_do_pdf(r.content)
    rasc = criar_rascunho(vendedor)
    r = client_vendedor.get(f"/pedidos/{rasc.pk}/pdf/", follow=True)
    assert "O PDF fica disponível depois de confirmar o pedido." in r.content.decode()
    assert r.redirect_chain == [(f"/pedidos/{rasc.pk}/", 302)]


def test_administrador_baixa_o_mesmo_pdf_sem_custo(client_admin, vendedor):
    produto = com_estoque(criar_produto(preco="125.00"), 5, "87.6543")
    ped = montar_pedido_confirmado(vendedor, itens=[(produto, 1)])
    r = client_admin.get(f"/pedidos/{ped.pk}/pdf/")
    texto = texto_do_pdf(r.content)
    assert r["Content-Type"] == "application/pdf" and "R$ 125,00" in texto
    for proibido in ["87,65", "87,6543", "Custo", "Lucro", "Margem"]:
        assert proibido not in texto


def test_pdf_do_cancelado_pelo_download(client_admin, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": "Cliente desistiu"})
    r = client_admin.get(f"/pedidos/{ped.pk}/pdf/")
    assert r["Content-Disposition"] == 'attachment; filename="pedido-1.pdf"'
    assert "CANCELADO" in texto_do_pdf(r.content)


def test_falha_ao_gerar_pdf_avisa(client_vendedor, vendedor, monkeypatch, caplog):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    monkeypatch.setattr(
        "apps.pedidos.views.gerar_pdf_pedido", Mock(side_effect=RuntimeError("falhou"))
    )
    r = client_vendedor.get(f"/pedidos/{ped.pk}/pdf/", follow=True)
    assert (
        "Não foi possível gerar o PDF. Tente de novo; se continuar, avise o administrador."
        in r.content.decode()
    )
    assert r.redirect_chain == [(f"/pedidos/{ped.pk}/", 302)]
    erros = [rec for rec in caplog.records if rec.exc_info]
    assert erros and erros[0].name == "helptoner.pdf"
    # O alerta (Sentry) leva o número interno do pedido, nunca dado do cliente.
    assert str(ped.pk) in erros[0].getMessage()


def test_detalhe_mostra_o_botao_do_pdf_so_fora_do_rascunho(
    client_vendedor, vendedor, administrador
):
    confirmado = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    cancelado = montar_pedido_confirmado(
        vendedor, itens=[(com_estoque(criar_produto("TN-1060"), 5), 1)]
    )
    cancelar_pedido(cancelado.pk, "Cliente desistiu", administrador)
    for pedido in (confirmado, cancelado):
        html = client_vendedor.get(f"/pedidos/{pedido.pk}/").content.decode()
        assert f'href="/pedidos/{pedido.pk}/pdf/"' in html
    rascunho = criar_rascunho(vendedor)
    assert "/pdf/" not in client_vendedor.get(f"/pedidos/{rascunho.pk}/").content.decode()


def test_rota_do_pdf_so_aceita_get_de_pedido_existente(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert client_vendedor.post(f"/pedidos/{ped.pk}/pdf/").status_code == 405
    assert client_vendedor.get("/pedidos/999999/pdf/").status_code == 404
