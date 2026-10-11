from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.pedidos.models import Pedido
from apps.pedidos.services import cancelar_pedido
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    montar_pedido_confirmado,
    montar_rascunho,
)

BRASILIA = timezone(timedelta(hours=-3))  # em 2026 não há horário de verão


def brt(*partes) -> datetime:
    """Data e hora de Brasília, como instante com fuso."""
    return datetime(*partes, tzinfo=BRASILIA)


@pytest.fixture
def cenario(administrador, vendedor):
    lucas, carla = administrador, vendedor
    c1 = criar_cliente("Papelaria Central Ltda")
    c2 = criar_cliente("Clínica Bem Viver")
    ce285a = com_estoque(criar_produto("CE285A", preco="100.00"), 100, "60.00", lucas)
    tn1060 = com_estoque(
        criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother", preco="50.00"),
        100,
        "20.00",
        lucas,
    )
    cf217a = criar_produto("CF217A", descricao="Toner HP 17A Preto", preco="80.00")

    pedido1 = montar_pedido_confirmado(
        carla, cliente=c1, itens=[(ce285a, 2), (tn1060, 1)], desconto=("percentual", "10")
    )
    pedido2 = montar_pedido_confirmado(lucas, cliente=c2, itens=[(ce285a, 1)])
    pedido3 = montar_pedido_confirmado(
        carla, cliente=c1, itens=[(tn1060, 3)], desconto=("reais", "15")
    )
    pedido4 = montar_pedido_confirmado(lucas, cliente=c2, itens=[(tn1060, 1)])
    cancelar_pedido(pedido4.pk, "Cliente desistiu", lucas)
    rascunho = montar_rascunho(carla, cliente=c1, itens=[(ce285a, 1)])

    datas = {
        pedido1: {"confirmado_em": brt(2026, 9, 15, 10, 0)},
        pedido2: {"confirmado_em": brt(2026, 9, 30, 22, 30)},
        pedido3: {"confirmado_em": brt(2026, 10, 2, 9, 0)},
        pedido4: {
            "confirmado_em": brt(2026, 10, 2, 11, 0),
            "cancelado_em": brt(2026, 10, 3, 10, 0),
        },
    }
    for pedido, campos in datas.items():
        Pedido.objects.filter(pk=pedido.pk).update(**campos)
        pedido.refresh_from_db()
    return SimpleNamespace(
        lucas=lucas, carla=carla, c1=c1, c2=c2, ce285a=ce285a, tn1060=tn1060, cf217a=cf217a,
        pedido1=pedido1, pedido2=pedido2, pedido3=pedido3, pedido4=pedido4, rascunho=rascunho,
    )  # fmt: skip
