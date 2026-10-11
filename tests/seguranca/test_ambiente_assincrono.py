import os


def test_variavel_assincrona_nao_vaza_para_os_testes_normais():
    assert "DJANGO_ALLOW_ASYNC_UNSAFE" not in os.environ
