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
