from apps.cadastros.models import Cliente
from tests.apoio import criar_cliente


def test_cadastrar_empresa(client_vendedor):
    client_vendedor.post(
        "/clientes/novo/",
        {
            "tipo": "PJ",
            "nome": "Papelaria Central Ltda",
            "documento": "11.222.333/0001-81",
            "cep": "13010-000",
            "uf": "SP",
            "cidade": "Campinas",
        },
    )
    c = Cliente.objects.get()
    assert (c.documento, c.cep, c.ativo, c.codigo) == ("11222333000181", "13010000", True, c.pk)


def test_documento_invalido_mostra_erro_e_nao_grava(client_vendedor):
    r = client_vendedor.post(
        "/clientes/novo/", {"tipo": "PJ", "nome": "X", "documento": "12.345.678/0001-99"}
    )
    assert "CNPJ inválido: confira os dígitos." in r.content.decode()
    assert not Cliente.objects.exists()


def test_cep_invalido_mostra_erro(client_vendedor):
    r = client_vendedor.post(
        "/clientes/novo/",
        {"tipo": "PJ", "nome": "X", "documento": "11.222.333/0001-81", "cep": "123"},
    )
    assert "CEP inválido: informe os 8 dígitos." in r.content.decode()
    assert not Cliente.objects.exists()


def test_documento_repetido_mostra_quem_ja_tem(client_vendedor):
    criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    r = client_vendedor.post(
        "/clientes/novo/", {"tipo": "PJ", "nome": "Outra", "documento": "11.222.333/0001-81"}
    )
    texto = r.content.decode()
    assert "Já existe um cliente com este CPF/CNPJ: Papelaria Central Ltda." in texto
    assert Cliente.objects.count() == 1


def test_editar_sem_mudar_o_documento_nao_acusa_repetido(client_vendedor):
    c = criar_cliente()
    r = client_vendedor.post(
        f"/clientes/{c.pk}/", {"tipo": c.tipo, "nome": "Novo nome", "documento": c.documento}
    )
    assert r.status_code == 302
    c.refresh_from_db()
    assert c.nome == "Novo nome"


def test_obrigatorios(client_vendedor):
    r = client_vendedor.post("/clientes/novo/", {"tipo": "PF"})
    assert r.content.decode().count("Este campo é obrigatório.") == 2  # documento e nome


def test_inativar_e_reativar(client_vendedor):
    c = criar_cliente()
    client_vendedor.post(f"/clientes/{c.pk}/inativar/")
    c.refresh_from_db()
    assert not c.ativo
    client_vendedor.post(f"/clientes/{c.pk}/reativar/")
    c.refresh_from_db()
    assert c.ativo


def test_inativar_so_aceita_post(client_vendedor):
    c = criar_cliente()
    assert client_vendedor.get(f"/clientes/{c.pk}/inativar/").status_code == 405
    assert client_vendedor.get(f"/clientes/{c.pk}/reativar/").status_code == 405


def test_alteracao_vai_para_o_historico(client_vendedor, vendedor):
    c = criar_cliente()
    dados = {
        "tipo": c.tipo,
        "nome": c.nome,
        "documento": c.documento,
        "telefone": "(19) 99999-0000",
    }
    client_vendedor.post(f"/clientes/{c.pk}/", dados)
    assert c.history.count() == 2
    assert c.history.first().history_user == vendedor


def test_lista_htmx_e_lista_vazia(client_vendedor):
    resposta = client_vendedor.get("/clientes/", headers={"HX-Request": "true"})
    assert "Nenhum cliente ainda. Cadastre o primeiro." in resposta.content.decode()
    criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    r = client_vendedor.get("/clientes/?q=joao", headers={"HX-Request": "true"})
    assert "João da Silva" in r.content.decode()
    assert "<html" not in r.content.decode()


def test_lista_sem_htmx_traz_a_pagina_com_esqueleto(client_vendedor):
    texto = client_vendedor.get("/clientes/").content.decode()
    assert "<html" in texto
    assert 'hx-trigger="load"' in texto


def test_lista_esconde_inativos_ate_pedir(client_vendedor):
    criar_cliente("Gráfica Antiga", ativo=False)
    cabecalho = {"HX-Request": "true"}
    assert (
        "Gráfica Antiga"
        not in client_vendedor.get("/clientes/", headers=cabecalho).content.decode()
    )
    r = client_vendedor.get("/clientes/?inativos=1", headers=cabecalho)
    assert "Gráfica Antiga" in r.content.decode()


def test_busca_sem_resultado_avisa(client_vendedor):
    criar_cliente("João da Silva", tipo="PF")
    r = client_vendedor.get("/clientes/?q=zzz", headers={"HX-Request": "true"})
    assert "Nenhum cliente encontrado." in r.content.decode()
