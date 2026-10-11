import re
from urllib.parse import urlsplit, urlunsplit

_CAMPOS_DA_REQUISICAO = ("cookies", "headers", "data", "query_string", "env")
# Linhas "DETAIL:" do PostgreSQL e trechos "Key (campo)=(valor)" trazem dados das linhas do banco.
_DETAIL = re.compile(r"\n?\s*DETAIL:.*", re.DOTALL)
_CHAVE = re.compile(r"Key \([^)]*\)=\(.*?\)(?=\s|$|\.)", re.DOTALL)


def _limpar_texto(texto):
    if not isinstance(texto, str):
        return texto
    return _CHAVE.sub("Key (...)=(...)", _DETAIL.sub("", texto))


def limpar_evento(evento: dict, dica: dict) -> dict:
    """before_send do Sentry: tira do evento tudo que pode ter dado pessoal (usuário, cookies,
    cabeçalhos, corpo, query e ambiente), tira dos textos de erro as linhas DETAIL e os trechos
    Key (...)=(...) do banco e deixa da requisição só o método e o caminho da URL, sem a query."""
    evento.pop("user", None)
    requisicao = evento.get("request")
    if requisicao:
        for campo in _CAMPOS_DA_REQUISICAO:
            requisicao.pop(campo, None)
        if requisicao.get("url"):
            partes = urlsplit(requisicao["url"])
            requisicao["url"] = urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))
    for valor in (evento.get("exception") or {}).get("values", []):
        if "value" in valor:
            valor["value"] = _limpar_texto(valor["value"])
    if "message" in evento:
        evento["message"] = _limpar_texto(evento["message"])
    logentry = evento.get("logentry")
    if logentry:
        for campo in ("message", "formatted"):
            if campo in logentry:
                logentry[campo] = _limpar_texto(logentry[campo])
        logentry.pop("params", None)
    return evento
