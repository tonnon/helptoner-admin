from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.e2e.conftest import entrar

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True, serialized_rollback=True)]


def test_exportar_relatorio(pagina, live_server, administrador):
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("link", name="Relatórios").click()
    pagina.get_by_role("link", name="Vendas por período", exact=True).click()
    with pagina.expect_download() as excel:
        pagina.get_by_role("link", name="⤓ Excel", exact=True).click()
    load_workbook(excel.value.path())
    with pagina.expect_download() as pdf:
        pagina.get_by_role("link", name="⤓ PDF", exact=True).click()
    assert Path(pdf.value.path()).read_bytes().startswith(b"%PDF-")
