import pytest

from apps.contas.navegador import navegador_legivel
from tests.apoio import UA_CHROME_WINDOWS


@pytest.mark.parametrize(
    "ua,esperado",
    [
        (UA_CHROME_WINDOWS, "Chrome no Windows"),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0 Safari/537.36 Edg/141.0",
            "Edge no Windows",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
            "Safari no iPhone",
        ),
        (
            "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0 Mobile Safari/537.36",
            "Chrome no Android",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Firefox no Mac",
        ),
        ("", "Navegador desconhecido"),
    ],
)
def test_navegador_legivel(ua, esperado):
    assert navegador_legivel(ua) == esperado
