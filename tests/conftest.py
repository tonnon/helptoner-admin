import pytest
from django.test import Client

from apps.contas.models import ADMINISTRADOR, VENDEDOR
from tests.apoio import criar_usuario


@pytest.fixture
def administrador(db):
    return criar_usuario(ADMINISTRADOR, email="lucas@helptoner.com.br", nome="Lucas Tonnon")


@pytest.fixture
def vendedor(db):
    return criar_usuario(VENDEDOR, email="carla@helptoner.com.br", nome="Carla Souza")


@pytest.fixture
def client_admin(administrador):
    client = Client()
    client.force_login(administrador)
    return client


@pytest.fixture
def client_vendedor(vendedor):
    client = Client()
    client.force_login(vendedor)
    return client
