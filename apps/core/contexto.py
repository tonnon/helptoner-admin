from dataclasses import dataclass
from functools import cache

from django.urls import NoReverseMatch, reverse
from django.utils.functional import SimpleLazyObject

from .permissoes import eh_administrador


@dataclass(frozen=True)
class ItemMenu:
    nome: str
    url_name: str
    icone: str  # nome do arquivo em templates/icones/, sem o .svg
    so_admin: bool


@dataclass(frozen=True)
class LinkMenu:
    """Item do menu pronto para o template, com a URL resolvida."""

    nome: str
    url_name: str
    url: str
    icone: str  # caminho do template do ícone


MENU = (
    ItemMenu("Início", "core:inicio", "inicio", so_admin=False),
    ItemMenu("Pedidos", "pedidos:lista", "pedidos", so_admin=False),
    ItemMenu("Clientes", "cadastros:clientes", "clientes", so_admin=False),
    ItemMenu("Produtos", "cadastros:produtos", "produtos", so_admin=False),
    ItemMenu("Estoque", "estoque:historico", "estoque", so_admin=False),
    ItemMenu("Relatórios", "relatorios:resumo", "relatorios", so_admin=True),
    ItemMenu("Funcionários", "contas:funcionarios", "funcionarios", so_admin=True),
    ItemMenu("Histórico", "core:historico", "historico", so_admin=True),
)


def itens_do_menu(usuario) -> list[ItemMenu]:
    """Os itens que o perfil do usuário pode ver, existindo a rota ou não."""
    if not usuario.is_authenticated:
        return []
    admin = eh_administrador(usuario)
    return [item for item in MENU if admin or not item.so_admin]


def _url_ou_none(url_name: str) -> str | None:
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def _links(usuario) -> list[LinkMenu]:
    links = []
    for item in itens_do_menu(usuario):
        url = _url_ou_none(item.url_name)
        if url is not None:  # a rota ainda não existe: o item fica de fora
            links.append(LinkMenu(item.nome, item.url_name, url, f"icones/{item.icone}.svg"))
    return links


def _ativo(links: list[LinkMenu], caminho: str) -> str:
    """O url_name do item cuja URL é o maior prefixo do caminho ("/" só vale para "/")."""

    def contem(link: LinkMenu) -> bool:
        return caminho == link.url or (link.url != "/" and caminho.startswith(link.url))

    candidatos = [link for link in links if contem(link)]
    return max(candidatos, key=lambda link: len(link.url)).url_name if candidatos else ""


def navegacao(request) -> dict:
    """Context processor do menu.

    `menu` e `menu_ativo` só são calculados se o template usar: as respostas parciais do
    HTMX e as páginas de erro não consultam o banco por causa do menu. Uma view pode
    passar `menu_ativo` no contexto para escolher outro item.
    """

    @cache
    def montar() -> tuple[list[LinkMenu], str]:
        usuario = getattr(request, "user", None)
        links = _links(usuario) if usuario is not None else []
        return links, _ativo(links, request.path)

    return {
        "menu": SimpleLazyObject(lambda: montar()[0]),
        "menu_ativo": SimpleLazyObject(lambda: montar()[1]),
        "url_minha_conta": _url_ou_none("contas:minha_conta"),
    }
