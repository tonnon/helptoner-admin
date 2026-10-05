from allauth.mfa.models import Authenticator

from tests.apoio import SENHA_TESTE


def test_minha_conta_mostra_dados_e_atalhos(client_vendedor):
    html = client_vendedor.get("/minha-conta/").content.decode()
    assert "carla@helptoner.com.br" in html and "Vendedor" in html
    assert "/contas/password/change/" in html and "/contas/2fa/recovery-codes/generate/" in html
    assert ">Trocar senha<" in html and ">Gerar novos códigos de recuperação<" in html
    assert '<a href="/minha-conta/" class="item-menu ativo" aria-current="page">' in html


def test_trocar_senha_exige_a_atual(client_vendedor):
    r = client_vendedor.post(
        "/contas/password/change/",
        {
            "oldpassword": "errada-errada-1",
            "password1": "toner-azul-de-março",
            "password2": "toner-azul-de-março",
        },
    )
    assert r.status_code == 200  # formulário com erro; senha mantida


def test_trocar_senha_volta_para_minha_conta(client_vendedor, vendedor):
    nova = "toner-azul-de-março"
    html = client_vendedor.get("/contas/password/change/").content.decode()
    assert ">Senha atual</label>" in html and ">Confirme a nova senha</label>" in html
    r = client_vendedor.post(
        "/contas/password/change/",
        {"oldpassword": SENHA_TESTE, "password1": nova, "password2": nova},
    )
    assert r["Location"] == "/minha-conta/"
    vendedor.refresh_from_db()
    assert vendedor.check_password(nova)
    assert client_vendedor.get("/minha-conta/").status_code == 200  # continua logado


def test_gerar_novos_codigos_pede_a_senha_e_mostra_os_novos(client_vendedor, vendedor):
    antigos = Authenticator.objects.get(user=vendedor, type=Authenticator.Type.RECOVERY_CODES)
    r = client_vendedor.get("/contas/2fa/recovery-codes/generate/")
    assert r["Location"].startswith("/contas/reauthenticate/")  # o force_login não é recente
    r = client_vendedor.post(r["Location"], {"password": SENHA_TESTE})
    assert r["Location"] == "/contas/2fa/recovery-codes/generate/"
    html = client_vendedor.get(r["Location"]).content.decode()
    assert "Os códigos atuais deixam de valer." in html
    r = client_vendedor.post("/contas/2fa/recovery-codes/generate/")
    assert r["Location"] == "/contas/2fa/recovery-codes/"
    html = client_vendedor.get("/contas/2fa/recovery-codes/").content.decode()
    novos = Authenticator.objects.get(user=vendedor, type=Authenticator.Type.RECOVERY_CODES)
    assert novos.pk != antigos.pk
    assert all(codigo in html for codigo in novos.wrap().get_unused_codes())
    assert "Guardei os códigos, continuar" not in html  # isso é só no primeiro acesso
    assert 'href="/minha-conta/"' in html and "/contas/2fa/recovery-codes/download/" in html


def test_tela_padrao_do_2fa_so_leva_para_minha_conta(client_vendedor):
    html = client_vendedor.get("/contas/2fa/").content.decode()
    assert 'href="/minha-conta/"' in html
    assert "/contas/2fa/totp/deactivate/" not in html
