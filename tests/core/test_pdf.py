import datetime as dt
from io import BytesIO

from django.utils import timezone
from pypdf import PdfReader

from apps.core.pdf import DocumentoPDF
from tests.apoio import texto_do_pdf

COLUNAS = [("Código", 30, "L"), ("Descrição", 90, "L"), ("Qtd.", 20, "R"), ("Total", 40, "R")]


def _linhas(quantas: int) -> list[list[str]]:
    return [
        [f"P{n:03d}", f"Produto de teste número {n}", str(n), f"R$ {n},00"]
        for n in range(1, quantas + 1)
    ]


def _paginas(doc: DocumentoPDF) -> list[str]:
    return [pagina.extract_text() for pagina in PdfReader(BytesIO(doc.para_bytes())).pages]


def test_titulo_subtitulo_e_rodape_com_a_hora_de_brasilia(monkeypatch):
    # 01/11/2026 01:30 em UTC ainda é 31/10/2026 22:30 em Brasília.
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 1, 1, 30, tzinfo=dt.UTC))
    dados = DocumentoPDF("Vendas por período", "01/09/2026 a 30/09/2026").para_bytes()
    texto = texto_do_pdf(dados)
    assert dados.startswith(b"%PDF-")
    assert "Vendas por período" in texto and "01/09/2026 a 30/09/2026" in texto
    assert "Página 1 de 1 · gerado em 31/10/2026 22:30" in texto


def test_tabela_quebra_a_pagina_e_repete_cabecalho_titulo_e_rodape():
    doc = DocumentoPDF("Lista de produtos")
    doc.tabela(COLUNAS, _linhas(120))
    paginas = _paginas(doc)
    assert len(paginas) >= 3
    for numero, texto in enumerate(paginas, start=1):
        assert "Lista de produtos" in texto
        assert "Código" in texto and "Descrição" in texto
        assert f"Página {numero} de {len(paginas)} · gerado em " in texto
    assert "P001" in paginas[0] and "P120" in paginas[-1]


def test_texto_longo_quebra_linha_na_celula_sem_perder_palavras():
    longo = " ".join(f"palavra{n}" for n in range(60))
    doc = DocumentoPDF("Teste")
    doc.tabela(COLUNAS, [["X1", longo, "1", "R$ 1,00"], ["X2", "curto", "2", "R$ 2,00"]])
    texto = texto_do_pdf(doc.para_bytes())
    assert "palavra0" in texto and "palavra59" in texto and "X2" in texto


def test_tabela_sem_linhas_so_tem_o_cabecalho():
    doc = DocumentoPDF("Vazio")
    doc.tabela(COLUNAS, [])
    assert "Descrição" in texto_do_pdf(doc.para_bytes())


def test_a4_em_retrato_e_em_paisagem():
    retrato = PdfReader(BytesIO(DocumentoPDF("A").para_bytes())).pages[0].mediabox
    paisagem = PdfReader(BytesIO(DocumentoPDF("A", orientacao="L").para_bytes())).pages[0].mediabox
    assert (round(retrato.width), round(retrato.height)) == (595, 842)
    assert (round(paisagem.width), round(paisagem.height)) == (842, 595)


def test_selo_sai_no_cabecalho_de_todas_as_paginas():
    doc = DocumentoPDF("Pedido nº 1", selo="CANCELADO")
    doc.tabela(COLUNAS, _linhas(100))
    paginas = _paginas(doc)
    assert len(paginas) >= 2
    assert all("CANCELADO" in texto for texto in paginas)


def test_sem_selo_nao_sai_nada_alem_do_titulo():
    assert "CANCELADO" not in texto_do_pdf(DocumentoPDF("Pedido nº 1").para_bytes())


def test_acentos_e_simbolos_saem_na_fonte_inter_embutida():
    doc = DocumentoPDF("Comércio — Relatório nº 1", "João & Cia · − R$ 10,00")
    doc.tabela(COLUNAS, [["ÀÉÎÕÜ", "çãõ ñ ü", "1", "− R$ 1,00"]])
    dados = doc.para_bytes()
    texto = texto_do_pdf(dados)
    for trecho in ["Comércio — Relatório nº 1", "João & Cia · − R$ 10,00", "ÀÉÎÕÜ", "çãõ ñ ü"]:
        assert trecho in texto
    # Só a Inter, e embutida no arquivo (nenhuma das fontes padrão do PDF).
    recursos = PdfReader(BytesIO(dados)).pages[0]["/Resources"]
    fontes = [fonte.get_object() for fonte in recursos["/Font"].values()]
    assert {fonte["/BaseFont"].split("+")[-1] for fonte in fontes} == {"Inter", "InterSemiBold"}
    assert b"/FontFile2" in dados


def test_caractere_que_a_fonte_nao_tem_nao_derruba_o_pdf():
    # Nomes de cliente e de produto vêm de digitação: emoji e ideogramas não podem impedir o PDF.
    doc = DocumentoPDF("Pedido 🙂 中文")
    doc.tabela(COLUNAS, [["X1", "Cliente 🙂 中文 Ltda", "1", "R$ 1,00"]])
    texto = texto_do_pdf(doc.para_bytes())
    assert "Cliente" in texto and "Ltda" in texto and "R$ 1,00" in texto
