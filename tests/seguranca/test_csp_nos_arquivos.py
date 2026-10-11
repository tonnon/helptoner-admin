import re

from django.conf import settings

BASE_DIR = settings.BASE_DIR

PROIBIDO_EM_TEMPLATES = [
    r"\sstyle\s*=",
    r"<script(?![^>]*\bsrc=)",
    r"\son[a-z]+\s*=",
    r"hx-on",
    r"javascript:",
]
PROIBIDO_NO_JS = [
    r"\beval\s*\(",
    r"new\s+Function",
    r"\.innerHTML\b",
    r"\.outerHTML\b",
    r"insertAdjacentHTML",
    r"setAttribute\(\s*['\"]style",
]


def _conferir(arquivos, padroes):
    assert arquivos, "nenhum arquivo para conferir"
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8")
        for padrao in padroes:
            assert not re.search(padrao, texto, re.I), f"{arquivo}: {padrao}"


def test_templates_respeitam_a_csp():
    _conferir(list((BASE_DIR / "templates").rglob("*.*")), PROIBIDO_EM_TEMPLATES)


def test_js_proprio_respeita_a_csp():  # só static/js/; static/vendor/ fica de fora
    _conferir(list((BASE_DIR / "static" / "js").rglob("*.js")), PROIBIDO_NO_JS)
