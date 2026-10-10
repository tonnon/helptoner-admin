import re
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.cadastros.forms import ProdutoForm
from apps.cadastros.models import Produto
from apps.estoque.models import MovimentoEstoque
from tests.apoio import com_estoque, criar_produto, montar_pedido_confirmado

DADOS = {"codigo": "CE285A", "descricao": "Toner HP 85A Preto", "marca": "HP", "preco": "189,90"}


def test_codigo_em_maiusculas_e_sem_espacos(client_admin):
    client_admin.post("/produtos/novo/", {**DADOS, "codigo": " ce285a "})
    p = Produto.objects.get()
    assert (p.codigo, p.preco, p.estoque, p.custo_medio) == (
        "CE285A",
        Decimal("189.90"),
        0,
        Decimal("0"),
    )


def test_codigo_repetido_em_outra_caixa(client_admin):
    criar_produto("CE285A")
    r = client_admin.post(
        "/produtos/novo/", {"codigo": "ce285a", "descricao": "X", "marca": "HP", "preco": "1"}
    )
    assert "Já existe um produto com este código." in r.content.decode()
    assert Produto.objects.count() == 1


def test_banco_barra_estoque_e_preco_negativos(db):
    p = criar_produto()
    with pytest.raises(IntegrityError), transaction.atomic():
        Produto.objects.filter(pk=p.pk).update(estoque=-1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Produto.objects.filter(pk=p.pk).update(preco=Decimal("-0.01"))


def test_preco_invalido_ou_negativo_mostra_erro(client_admin):
    for ruim in ("abc", "-1", "1,2,3"):
        r = client_admin.post("/produtos/novo/", {**DADOS, "preco": ruim})
        assert r.status_code == 200, ruim
        assert "preço" in r.content.decode().lower()
    assert not Produto.objects.exists()


def test_preco_com_milhar(client_admin):
    client_admin.post("/produtos/novo/", {**DADOS, "preco": "1.234,50"})
    assert Produto.objects.get().preco == Decimal("1234.50")


def test_estoque_e_custo_nao_mudam_pelo_formulario(client_admin):
    p = criar_produto()
    client_admin.post(f"/produtos/{p.pk}/", {**DADOS, "estoque": "99", "custo_medio": "1"})
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio) == (0, Decimal("0"))


def test_vendedor_consulta_mas_nao_edita(client_vendedor):
    p = criar_produto()
    assert client_vendedor.get("/produtos/").status_code == 200
    r = client_vendedor.get(f"/produtos/{p.pk}/")
    assert r.status_code == 200
    assert 'name="descricao"' not in r.content.decode()
    r = client_vendedor.post(f"/produtos/{p.pk}/", {**DADOS, "descricao": "Outro"})
    assert r.status_code == 403
    p.refresh_from_db()
    assert p.descricao == "Toner HP 85A Preto"


def test_mudanca_de_preco_vai_para_o_historico(client_admin, administrador):
    p = criar_produto(preco="179.90")
    client_admin.post(f"/produtos/{p.pk}/", {**DADOS, "descricao": p.descricao})
    novo, antigo = p.history.all()[:2]
    assert [(m.field, m.old, m.new) for m in novo.diff_against(antigo).changes] == [
        ("preco", Decimal("179.90"), Decimal("189.90"))
    ]


def test_admin_ve_estoque_e_custo_so_para_leitura(client_admin):
    p = criar_produto()
    html = client_admin.get(f"/produtos/{p.pk}/").content.decode()
    assert "O estoque muda só por movimentos (Estoque → Entrada ou Ajuste)." in html
    assert 'name="estoque"' not in html and 'name="custo_medio"' not in html


def test_inativar_e_reativar(client_admin):
    p = criar_produto()
    client_admin.post(f"/produtos/{p.pk}/inativar/")
    p.refresh_from_db()
    assert not p.ativo
    client_admin.post(f"/produtos/{p.pk}/reativar/")
    p.refresh_from_db()
    assert p.ativo


def test_lista_vazia_e_sem_resultado(client_vendedor):
    h = {"HX-Request": "true"}
    assert "Nenhum produto ainda." in client_vendedor.get("/produtos/", headers=h).content.decode()
    criar_produto()
    html = client_vendedor.get("/produtos/?q=zzz", headers=h).content.decode()
    assert "Nenhum produto encontrado." in html and "ainda" not in html


def test_lista_com_selos_de_estoque_e_filtro_de_marca(client_vendedor):
    for codigo, marca, estoque in (("A1", "HP", 12), ("B1", "Brother", 3), ("C1", "HP", 0)):
        p = criar_produto(codigo, marca=marca)
        Produto.objects.filter(pk=p.pk).update(estoque=estoque)
    h = {"HX-Request": "true"}
    html = client_vendedor.get("/produtos/?marca=Brother", headers=h).content.decode()
    assert "B1" in html and "A1" not in html
    html = client_vendedor.get("/produtos/", headers=h).content.decode()
    assert "etiqueta-verde" in html and "etiqueta-ambar" in html and "etiqueta-vermelho" in html


def test_filtros_nao_usam_changed_em_checkbox_nem_select(client_vendedor):
    html = client_vendedor.get("/produtos/").content.decode()
    gatilho = re.search(r'hx-trigger="([^"]*input changed[^"]*)"', html).group(1)
    partes = [p.strip() for p in gatilho.split(",")]
    for nome in ("inativos", "marca"):
        assert any(p.startswith("change from:") and nome in p for p in partes)
        assert not any("changed" in p and nome in p for p in partes)


def test_paginacao(client_vendedor):
    for i in range(21):
        criar_produto(f"P{i:02d}")
    h = {"HX-Request": "true"}
    p1 = client_vendedor.get("/produtos/", headers=h).content.decode()
    assert "1–20 de 21" in p1 and "P20" not in p1
    assert "P20" in client_vendedor.get("/produtos/?pagina=2", headers=h).content.decode()


def _corrida(monkeypatch, codigo):
    """Outro envio grava o mesmo código depois da conferência do formulário e antes do save."""
    original = ProdutoForm.is_valid

    def is_valid(self):
        valido = original(self)
        if valido:
            criar_produto(codigo, descricao="Concorrente")
        return valido

    monkeypatch.setattr(ProdutoForm, "is_valid", is_valid)


def test_corrida_no_codigo_ao_criar_vira_erro_de_campo(client_admin, monkeypatch):
    _corrida(monkeypatch, "CE285A")
    r = client_admin.post("/produtos/novo/", DADOS)
    assert r.status_code == 200
    assert "Já existe um produto com este código." in r.content.decode()
    assert Produto.objects.count() == 1


def test_corrida_no_codigo_ao_editar_vira_erro_de_campo(client_admin, monkeypatch):
    p = criar_produto("X-1")
    _corrida(monkeypatch, "CE285A")
    r = client_admin.post(f"/produtos/{p.pk}/", DADOS)
    assert r.status_code == 200
    assert "Já existe um produto com este código." in r.content.decode()


# Perda de atualização (revisão final, C1): estoque e custo médio só mudam por movimento. Quem
# abriu o produto antes de um movimento não pode gravar por cima o estoque e o custo que leu.


def _corrida_com_entrada(monkeypatch, produto, por):
    """Uma entrada de estoque acontece depois da conferência do formulário e antes do save."""
    original = ProdutoForm.is_valid

    def is_valid(self):
        valido = original(self)
        if valido:
            com_estoque(produto, 5, custo="200.00", por=por)
        return valido

    monkeypatch.setattr(ProdutoForm, "is_valid", is_valid)


def test_formulario_aberto_antes_de_venda_e_entrada_nao_desfaz_o_estoque(administrador):
    p = com_estoque(criar_produto(), 10, por=administrador)
    form = ProdutoForm({**DADOS, "preco": "199,90"}, instance=Produto.objects.get(pk=p.pk))
    assert form.is_valid()
    montar_pedido_confirmado(administrador, itens=[(p, 4)])
    com_estoque(p, 5, custo="200.00", por=administrador)
    form.save()
    p.refresh_from_db()
    ultimo = MovimentoEstoque.objects.filter(produto=p).latest("pk")
    assert (p.preco, p.estoque, p.custo_medio) == (Decimal("199.90"), 11, Decimal("145.4545"))
    assert (p.estoque, p.custo_medio) == (ultimo.estoque_apos, ultimo.custo_medio_apos)


def test_editar_pela_tela_durante_uma_entrada_mantem_estoque_e_custo(
    client_admin, administrador, monkeypatch
):
    p = com_estoque(criar_produto(), 10, por=administrador)
    _corrida_com_entrada(monkeypatch, p, administrador)
    r = client_admin.post(f"/produtos/{p.pk}/", {**DADOS, "preco": "199,90"})
    assert r.status_code == 302
    p.refresh_from_db()
    assert (p.preco, p.estoque, p.custo_medio) == (Decimal("199.90"), 15, Decimal("133.3333"))


def test_save_completo_de_instancia_antiga_nao_grava_estoque_nem_custo(administrador):
    # O caminho do painel de manutenção (ProdutoAdmin) e de qualquer outro save() completo.
    p = com_estoque(criar_produto(), 10, por=administrador)
    antigo = Produto.objects.get(pk=p.pk)
    com_estoque(p, 5, custo="200.00", por=administrador)
    antigo.descricao = "Toner HP 85A Preto Original"
    antigo.save()
    p.refresh_from_db()
    assert (p.descricao, p.estoque, p.custo_medio) == (
        "Toner HP 85A Preto Original",
        15,
        Decimal("133.3333"),
    )


def test_editar_pela_tela_nao_desfaz_inativacao_feita_em_outra_tela(client_admin, monkeypatch):
    p = criar_produto()
    original = ProdutoForm.is_valid

    def is_valid(self):
        valido = original(self)
        Produto.objects.filter(pk=p.pk).update(ativo=False)
        return valido

    monkeypatch.setattr(ProdutoForm, "is_valid", is_valid)
    assert client_admin.post(f"/produtos/{p.pk}/", {**DADOS, "preco": "199,90"}).status_code == 302
    p.refresh_from_db()
    assert (p.preco, p.ativo) == (Decimal("199.90"), False)
    assert p.history.first().ativo is False  # o histórico não registra reativação que não houve
