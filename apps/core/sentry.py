from urllib.parse import urlsplit, urlunsplit

_CAMPOS_DA_REQUISICAO = ("cookies", "headers", "data", "query_string", "env")


def limpar_evento(evento: dict, dica: dict) -> dict:
    """before_send do Sentry: tira do evento tudo que pode ter dado pessoal (usuário, cookies,
    cabeçalhos, corpo, query e ambiente) e deixa só o método e o caminho da URL, sem a query."""
    evento.pop("user", None)
    requisicao = evento.get("request")
    if requisicao:
        for campo in _CAMPOS_DA_REQUISICAO:
            requisicao.pop(campo, None)
        if requisicao.get("url"):
            partes = urlsplit(requisicao["url"])
            requisicao["url"] = urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))
    return evento
