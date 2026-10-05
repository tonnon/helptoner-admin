import json

from django import forms
from django.contrib import messages
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.paginator import Paginator
from django.template.loader import render_to_string

from apps.contas.models import Usuario
from apps.core.contexto import itens_do_menu, navegacao


def _nomes(usuario):
    return [item.nome for item in itens_do_menu(usuario)]


def test_menu_por_perfil(administrador, vendedor):
    assert _nomes(vendedor) == ["Início", "Pedidos", "Clientes", "Produtos", "Estoque"]
    assert _nomes(administrador) == [
        "Início",
        "Pedidos",
        "Clientes",
        "Produtos",
        "Estoque",
        "Relatórios",
        "Funcionários",
        "Histórico",
    ]


def test_base_usa_so_arquivos_locais_e_htmx_seguro(client_vendedor):
    html = client_vendedor.get("/").content.decode()
    assert "vendor/htmx.min.js" in html and "css/app.css" in html and "img/logo-helptoner" in html
    assert "https://" not in html
    config = html.split('name="htmx-config" content=\'')[1].split("'")[0]
    assert json.loads(config) == {
        "allowEval": False,
        "includeIndicatorStyles": False,
        "historyCacheSize": 0,
        "refreshOnHistoryMiss": True,
    }
    assert "hx-headers=" in html and "X-CSRFToken" in html


def test_menu_mostra_so_as_rotas_que_existem(client_admin):
    html = client_admin.get("/").content.decode()
    assert 'href="/" class="item-menu ativo" aria-current="page"' in html
    assert '<a href="/funcionarios/" class="item-menu">' in html and "Funcionários" in html
    assert "Relatórios" not in html  # rota ainda não existe
    assert '<a href="/minha-conta/" class="item-menu">' in html and "Minha conta" in html


def test_inicio_e_bloco_do_usuario_com_sair(client_admin):
    html = client_admin.get("/").content.decode()
    assert "Olá, Lucas" in html and "Administrador" in html
    assert 'method="post" action="/contas/logout/"' in html and "Sair" in html


def test_menu_so_e_montado_se_o_template_usar(rf, vendedor, django_assert_num_queries):
    request = rf.get("/")
    request.user = Usuario.objects.get(pk=vendedor.pk)  # sem os grupos em cache
    with django_assert_num_queries(0):
        contexto = navegacao(request)
    with django_assert_num_queries(1):  # os grupos do usuário
        assert [link.nome for link in contexto["menu"]] == ["Início", "Clientes", "Produtos"]
    assert contexto["menu_ativo"] == "core:inicio"
    assert contexto["url_minha_conta"] == "/minha-conta/"


def test_mensagens_do_django_viram_avisos(rf, vendedor):
    request = rf.get("/")
    request.user = vendedor
    request._messages = CookieStorage(request)
    messages.success(request, "Cliente salvo.")
    html = render_to_string("core/inicio.html", request=request)
    assert "Cliente salvo." in html and 'class="toast"' in html


def _componente(rf, nome, **contexto):
    request = rf.get("/pedidos/", {"busca": "ana"})
    return render_to_string(f"componentes/{nome}.html", contexto, request=request)


def test_paginacao_mantem_os_filtros(rf):
    html = _componente(rf, "paginacao", pagina=Paginator(range(38), 20).page(1))
    assert "1–20 de 38" in html and 'href="?busca=ana&amp;pagina=2"' in html


def test_selo_vazio_e_esqueleto(rf):
    selo = _componente(rf, "selo_status", status="confirmado")
    assert 'class="selo-confirmado"' in selo and "Confirmado" in selo
    vazio = _componente(rf, "vazio", mensagem="Nenhum ainda.", acao_url="/x/", acao_texto="Novo")
    assert "Nenhum ainda." in vazio and 'href="/x/"' in vazio
    assert _componente(rf, "esqueleto_linhas", linhas=3).count("ml-auto") == 3


def test_dialogo_com_motivo(rf):
    html = _componente(
        rf,
        "dialogo",
        id="cancelar",
        titulo="Cancelar?",
        acao_url="/c/",
        botao="Cancelar",
        perigo=True,
        campo_motivo=True,
    )
    assert '<dialog id="cancelar"' in html and 'name="motivo"' in html
    assert "btn-perigo" in html and "csrfmiddlewaretoken" in html


def test_campo_com_erro(rf):
    class Formulario(forms.Form):
        nome = forms.CharField(label="Nome")

    html = _componente(rf, "campo", campo=Formulario({"nome": ""})["nome"])
    assert ">Nome</label>" in html and "campo-invalido" in html
    assert 'id="id_nome_error"' in html and 'aria-describedby="id_nome_error"' in html
