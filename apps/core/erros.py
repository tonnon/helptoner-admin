class RegraDeNegocio(Exception):
    """Violação de uma regra de negócio, com mensagem pronta para mostrar ao usuário."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EstoqueInsuficiente(RegraDeNegocio):
    """O estoque não cobre a quantidade pedida."""
