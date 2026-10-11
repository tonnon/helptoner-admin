"""Base dos PDFs do sistema: o do pedido e, depois, os dos relatórios.

Página A4 em Inter, com o logo e o título no alto de todas as páginas e o rodapé "Página X de Y".
A fonte, a licença e o logo ficam em `pdf_recursos/`, dentro do pacote, para irem junto com o
código na função da Vercel. O arquivo é montado na memória e nada é gravado em disco.
"""

from pathlib import Path
from typing import Literal

from django.utils import timezone
from fpdf import FPDF, FontFace
from fpdf.enums import XPos, YPos
from fpdf.pattern import LinearGradient

from .formatacao import data_hora_br

RECURSOS = Path(__file__).resolve().parent / "pdf_recursos"
FONTE = "Inter"

# Cores da identidade visual (§6.1), em RGB.
TINTA = (14, 16, 36)
TEXTO_2 = (90, 95, 120)
LINHA = (230, 232, 241)
FUNDO = (245, 246, 251)
VERMELHO_TEXTO = (214, 0, 0)

MARGEM = 15  # mm, nos lados e no alto
ESPACO_PARA_O_RODAPE = 18  # mm livres embaixo, onde o texto do corpo não chega
LARGURA_DO_LOGO = 34  # mm; a altura segue a proporção do PNG
CORPO = 9  # pt
ESPACO_DEPOIS_DO_TITULO = 25  # mm: o título de uma seção não fica sozinho no fim da página


class DocumentoPDF(FPDF):
    """Documento A4 com cabeçalho e rodapé do sistema.

    `titulo` e `subtitulo` saem no alto de todas as páginas, ao lado do logo. `selo` (opcional)
    é uma marca em vermelho no canto de todas as páginas, como "CANCELADO". Use `secao` e
    `tabela` para o corpo, e `para_bytes` no fim. Quem precisar de mais usa a API do FPDF.
    """

    def __init__(
        self,
        titulo: str,
        subtitulo: str = "",
        orientacao: Literal["P", "L"] = "P",
        *,
        selo: str = "",
    ):
        super().__init__(orientation=orientacao, unit="mm", format="A4")
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.selo = selo
        self.gerado_em = data_hora_br(timezone.now())  # a hora de Brasília, a mesma em toda página
        self.set_title(titulo)
        self.set_author("Helptoner")
        self.set_lang("pt-BR")
        self.add_font(FONTE, "", RECURSOS / "Inter-Regular.ttf")
        self.add_font(FONTE, "B", RECURSOS / "Inter-SemiBold.ttf")  # o "negrito" é o SemiBold
        self.set_margins(MARGEM, MARGEM, MARGEM)
        self.set_auto_page_break(True, margin=ESPACO_PARA_O_RODAPE)
        self.alias_nb_pages()
        self.add_page()  # chama o header; as fontes e as margens já precisam estar prontas

    # ---------- Cabeçalho e rodapé (o FPDF chama em cada página) ----------

    def header(self) -> None:
        # A faixa em degradê vermelho → azul das telas, na borda de cima.
        degrade = LinearGradient(0, 0, self.w, 0, colors=["#FF0000", "#8A00C8", "#0200FF"])
        with self.use_pattern(degrade):
            self.rect(0, 0, self.w, 2, style="F")

        topo = 8
        logo = self.image(str(RECURSOS / "logo-helptoner.png"), x=MARGEM, y=topo, w=LARGURA_DO_LOGO)

        direita = self.w - self.r_margin
        largura_do_selo = 0.0
        if self.selo:
            largura_do_selo = self._desenhar_selo(direita, topo)
        x_texto = MARGEM + LARGURA_DO_LOGO + 6
        largura_do_texto = direita - largura_do_selo - (4 if self.selo else 0) - x_texto

        self.set_xy(x_texto, topo + 0.5)
        self.set_font(FONTE, "B", 16)
        self.set_text_color(*TINTA)
        self.cell(largura_do_texto, 8, self.titulo, new_x=XPos.LEFT, new_y=YPos.NEXT)
        if self.subtitulo:
            self.set_font(FONTE, "", CORPO)
            self.set_text_color(*TEXTO_2)
            self.multi_cell(largura_do_texto, 4.5, self.subtitulo, new_x=XPos.LEFT, new_y=YPos.NEXT)

        base = max(self.get_y(), topo + logo.rendered_height) + 3
        self.set_draw_color(*LINHA)
        self.set_line_width(0.3)
        self.line(MARGEM, base, direita, base)
        self.set_xy(self.l_margin, base + 5)  # o corpo começa aqui, em toda página
        self.set_font(FONTE, "", CORPO)
        self.set_text_color(*TINTA)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_draw_color(*LINHA)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(self.get_y() + 2)
        self.set_font(FONTE, "", 8)
        self.set_text_color(*TEXTO_2)
        # {nb} vira o total de páginas quando o arquivo é fechado (alias_nb_pages).
        texto = f"Página {self.page_no()} de {{nb}} · gerado em {self.gerado_em}"
        self.cell(0, 5, texto, align="C")

    def _desenhar_selo(self, direita: float, topo: float) -> float:
        """A marca com borda vermelha, encostada na margem da direita. Devolve a largura dela."""
        self.set_font(FONTE, "B", 11)
        largura = self.get_string_width(self.selo) + 8
        x = direita - largura
        self.set_draw_color(*VERMELHO_TEXTO)
        self.set_text_color(*VERMELHO_TEXTO)
        self.set_line_width(0.5)
        self.rect(x, topo + 1, largura, 8, style="D", round_corners=True, corner_radius=1.5)
        self.set_xy(x, topo + 1)
        self.cell(largura, 8, self.selo, align="C")
        return largura

    # ---------- Corpo ----------

    def secao(self, titulo: str) -> None:
        """Título de uma parte do documento ("Cliente", "Itens"), com um fio embaixo."""
        if self.will_page_break(ESPACO_DEPOIS_DO_TITULO):
            self.add_page()
        self.set_font(FONTE, "B", 10)
        self.set_text_color(*TINTA)
        self.cell(0, 6, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINHA)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y() + 0.5, self.w - self.r_margin, self.get_y() + 0.5)
        self.set_y(self.get_y() + 3)
        self.set_font(FONTE, "", CORPO)

    def tabela(self, colunas: list[tuple[str, float, str]], linhas: list[list[str]]) -> None:
        """Tabela com cabeçalho que se repete em cada página.

        Cada coluna é `(rótulo, largura em mm, alinhamento)`, com o alinhamento "L", "R" ou "C".
        Texto longo quebra em mais linhas dentro da célula. Cada linha de `linhas` tem um texto
        por coluna.
        """
        larguras = tuple(largura for _, largura, _ in colunas)
        self.set_font(FONTE, "", CORPO)
        self.set_text_color(*TINTA)
        self.set_draw_color(*LINHA)
        self.set_line_width(0.2)
        with self.table(
            col_widths=larguras,
            width=sum(larguras),
            align="LEFT",
            text_align=tuple(alinhamento for _, _, alinhamento in colunas),
            borders_layout="HORIZONTAL_LINES",
            headings_style=FontFace(emphasis="BOLD", color=TINTA, fill_color=FUNDO),
            line_height=5,
            padding=(1.4, 1),  # o texto fica alinhado com o dos títulos e dos totais
        ) as tabela:
            cabecalho = tabela.row()
            for rotulo, _, _ in colunas:
                cabecalho.cell(rotulo)
            for linha in linhas:
                registro = tabela.row()
                for texto in linha:
                    registro.cell(texto)
        self.set_x(self.l_margin)

    def para_bytes(self) -> bytes:
        return bytes(self.output())
