import pytest
from django.core.exceptions import ValidationError

from apps.cadastros.documentos import (
    cnpj_valido,
    cpf_valido,
    digitos_verificadores_cnpj,
    digitos_verificadores_cpf,
    formatar_documento,
    validar_documento,
)
from apps.cadastros.templatetags.cadastros import documento


@pytest.mark.parametrize("doc", ["12345678909", "52998224725"])
def test_cpf_valido(doc):
    assert cpf_valido(doc)


@pytest.mark.parametrize("doc", ["12345678900", "11111111111", "1234567890", "1234567890A", ""])
def test_cpf_invalido(doc):
    assert not cpf_valido(doc)


@pytest.mark.parametrize("doc", ["11222333000181", "12ABC34501DE35"])
def test_cnpj_valido(doc):
    assert cnpj_valido(doc)


@pytest.mark.parametrize(
    "doc",
    [
        "12345678000199",
        "00000000000000",
        "12ABC34501DE36",
        "12abc34501de35",
        "12ABC34501DEAB",
        "1122233300018",
    ],
)
def test_cnpj_invalido(doc):
    assert not cnpj_valido(doc)


def test_digitos_verificadores():
    assert digitos_verificadores_cnpj("12ABC34501DE") == "35"
    assert digitos_verificadores_cpf("123456789") == "09"


def test_validar_documento_aceita_mascara_e_minusculas():
    assert validar_documento("PJ", "12.abc.345/01de-35") == "12ABC34501DE35"
    assert validar_documento("PF", "123.456.789-09") == "12345678909"
    with pytest.raises(ValidationError, match="CNPJ inválido: confira os dígitos."):
        validar_documento("PJ", "12.345.678/0001-99")
    with pytest.raises(ValidationError, match="CPF inválido: confira os dígitos."):
        validar_documento("PF", "11.222.333/0001-81")


def test_formatar_documento():
    assert formatar_documento("PF", "12345678909") == "123.456.789-09"
    assert formatar_documento("PJ", "12ABC34501DE35") == "12.ABC.345/01DE-35"


def test_filtro_documento():
    assert documento("12345678909", "PF") == "123.456.789-09"
    assert documento("12ABC34501DE35", "PJ") == "12.ABC.345/01DE-35"
