"""Estrutura comum das tabelas dos relatórios (tela, PDF e Excel leem a mesma)."""

from dataclasses import dataclass
from typing import Literal

TipoColuna = Literal["texto", "dinheiro", "inteiro", "percentual", "data"]


@dataclass(frozen=True)
class Coluna:
    rotulo: str
    tipo: TipoColuna


@dataclass(frozen=True)
class Tabela:
    titulo: str
    colunas: list[Coluna]
    linhas: list[list[object]]
    # Só a tela usa (as exportações ignoram): o id do pedido de cada linha que o botão
    # "Repetir pedido" copia.
    pedidos_a_repetir: list[int] | None = None

    def linhas_da_tela(self) -> list[tuple[list[tuple[Coluna, object]], int | None]]:
        """Cada linha como (células, pedido a repetir ou None); cada célula é (coluna, valor)."""
        pedidos = self.pedidos_a_repetir or [None] * len(self.linhas)
        return [
            (list(zip(self.colunas, linha, strict=True)), pedido)
            for linha, pedido in zip(self.linhas, pedidos, strict=True)
        ]
