"""O PDF do pedido, para entregar ao cliente: sem custo, lucro nem margem, para qualquer perfil."""

from django.template.defaultfilters import floatformat
from fpdf.enums import XPos, YPos

from apps.cadastros.documentos import formatar_documento
from apps.cadastros.models import Cliente, TipoPessoa
from apps.core.formatacao import brl, data_hora_br, inteiro_br, numero_pedido
from apps.core.pdf import CORPO, FONTE, TEXTO_2, TINTA, VERMELHO_TEXTO, DocumentoPDF

from .models import Pedido

COLUNAS = [
    ("Código", 28, "L"),
    ("Descrição", 82, "L"),
    ("Qtd.", 16, "R"),
    ("Unit.", 27, "R"),
    ("Total", 27, "R"),
]
LARGURA_DOS_TOTAIS = 80  # mm, encostados na margem da direita
ALTURA_DA_LINHA_DE_TOTAL = 6.5  # mm


def gerar_pdf_pedido(pedido: Pedido) -> bytes:
    """O PDF de um pedido confirmado ou cancelado (só eles têm número). O cancelado sai marcado."""
    cancelado = pedido.status == Pedido.Status.CANCELADO
    doc = DocumentoPDF(
        f"Pedido {numero_pedido(pedido.numero)}",
        f"Confirmado em {data_hora_br(pedido.confirmado_em)}"
        f" · Emitido por {pedido.criado_por.primeiro_nome}",
        selo="CANCELADO" if cancelado else "",
    )
    if cancelado:
        _aviso_de_cancelamento(doc, pedido)
    _cliente(doc, pedido.cliente)
    _itens(doc, pedido)
    _totais(doc, pedido)
    if pedido.observacoes:
        doc.secao("Observações")
        doc.multi_cell(0, 5, pedido.observacoes, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return doc.para_bytes()


def _aviso_de_cancelamento(doc: DocumentoPDF, pedido: Pedido) -> None:
    """Quadro vermelho no alto do corpo: quando, quem e por quê."""
    largura = doc.w - doc.l_margin - doc.r_margin
    topo = doc.get_y()
    doc.set_xy(doc.l_margin + 4, topo + 3)
    doc.set_font(FONTE, "B", 10)
    doc.set_text_color(*VERMELHO_TEXTO)
    quando = data_hora_br(pedido.cancelado_em)
    quem = pedido.cancelado_por.primeiro_nome
    doc.cell(largura - 8, 5, f"CANCELADO em {quando} por {quem}", new_x=XPos.LEFT, new_y=YPos.NEXT)
    doc.set_font(FONTE, "", CORPO)
    doc.set_text_color(*TINTA)
    doc.multi_cell(
        largura - 8, 5, f"Motivo: {pedido.motivo_cancelamento}", new_x=XPos.LEFT, new_y=YPos.NEXT
    )
    fim = doc.get_y() + 3
    doc.set_draw_color(*VERMELHO_TEXTO)
    doc.set_line_width(0.5)
    doc.rect(
        doc.l_margin, topo, largura, fim - topo, style="D", round_corners=True, corner_radius=1.5
    )
    doc.set_xy(doc.l_margin, fim + 6)


def _cliente(doc: DocumentoPDF, cliente: Cliente) -> None:
    doc.secao("Cliente")
    doc.set_font(FONTE, "B", 11)
    doc.multi_cell(0, 6, cliente.nome, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.set_font(FONTE, "", CORPO)
    doc.set_text_color(*TEXTO_2)
    for linha in _linhas_do_cliente(cliente):
        doc.multi_cell(0, 5, linha, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.set_text_color(*TINTA)
    doc.ln(5)


def _linhas_do_cliente(cliente: Cliente) -> list[str]:
    """Documento, contato e endereço do cadastro; o que está em branco não vira linha."""
    rotulo = "CPF" if cliente.tipo == TipoPessoa.PF else "CNPJ"
    contato = [
        f"Telefone {cliente.telefone}" if cliente.telefone else "",
        f"E-mail {cliente.email}" if cliente.email else "",
    ]
    rua = ", ".join(parte for parte in (cliente.logradouro, cliente.numero) if parte)
    if cliente.complemento:
        rua = f"{rua} - {cliente.complemento}" if rua else cliente.complemento
    cidade = "/".join(parte for parte in (cliente.cidade, cliente.uf) if parte)
    cep = f"CEP {_formatar_cep(cliente.cep)}" if cliente.cep else ""
    bairro_e_cidade = " - ".join(parte for parte in (cliente.bairro, cidade, cep) if parte)
    linhas = [
        f"{rotulo} {formatar_documento(cliente.tipo, cliente.documento)}",
        " · ".join(parte for parte in contato if parte),
        rua,
        bairro_e_cidade,
    ]
    return [linha for linha in linhas if linha]


def _formatar_cep(cep: str) -> str:
    """O cadastro guarda os 8 dígitos sem máscara: '01234567' → '01234-567'."""
    return f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep


def _itens(doc: DocumentoPDF, pedido: Pedido) -> None:
    doc.secao("Itens")
    doc.tabela(
        COLUNAS,
        [
            [
                item.codigo,
                item.descricao,
                inteiro_br(item.quantidade),
                brl(item.preco_unitario),
                brl(item.total),
            ]
            for item in pedido.itens.all()
        ],
    )
    doc.ln(4)


def _totais(doc: DocumentoPDF, pedido: Pedido) -> None:
    """Subtotal, desconto (só se houver, como na tela do pedido) e total, juntos no fim."""
    linhas = [("Subtotal", brl(pedido.subtotal))]
    if pedido.desconto_valor > 0:
        rotulo = "Desconto"
        if pedido.desconto_tipo == Pedido.TipoDesconto.PERCENTUAL:
            rotulo += f" ({floatformat(pedido.desconto_informado, '-2')}%)"
        linhas.append((rotulo, f"− {brl(pedido.desconto_valor)}"))
    if doc.will_page_break(ALTURA_DA_LINHA_DE_TOTAL * (len(linhas) + 1) + 4):
        doc.add_page()  # os totais não se separam em duas páginas
    x = doc.w - doc.r_margin - LARGURA_DOS_TOTAIS
    for rotulo, valor in linhas:
        _linha_de_total(doc, x, rotulo, valor, negrito=False)
    doc.set_draw_color(*TINTA)
    doc.set_line_width(0.3)
    doc.line(x, doc.get_y() + 1, doc.w - doc.r_margin, doc.get_y() + 1)
    doc.set_y(doc.get_y() + 2)
    _linha_de_total(doc, x, "Total", brl(pedido.total), negrito=True)


def _linha_de_total(doc: DocumentoPDF, x: float, rotulo: str, valor: str, *, negrito: bool) -> None:
    doc.set_font(FONTE, "B" if negrito else "", 12 if negrito else CORPO)
    doc.set_x(x)
    metade = LARGURA_DOS_TOTAIS / 2
    doc.cell(metade, ALTURA_DA_LINHA_DE_TOTAL, rotulo)
    doc.cell(
        metade, ALTURA_DA_LINHA_DE_TOTAL, valor, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    doc.set_font(FONTE, "", CORPO)
