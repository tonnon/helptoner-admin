from apps.pedidos.templatetags.pedidos import realce


def test_realce():
    assert realce("João da Silva", "joao") == "<mark>João</mark> da Silva"
    assert realce("<b>x</b>", "b") == "&lt;<mark>b</mark>&gt;x&lt;/b&gt;"
    assert realce("abc", "") == "abc"


def test_realce_ignora_acento_e_maiuscula_dos_dois_lados():
    assert realce("Café Ltda", "CAFE") == "<mark>Café</mark> Ltda"
    assert realce("Joao Pereira", "joão") == "<mark>Joao</mark> Pereira"
    assert realce("Toner HP 85A", "hp 85") == "Toner <mark>HP 85</mark>A"


def test_realce_sem_trecho_igual_so_escapa():
    assert realce("x & y", "z") == "x &amp; y"
    assert realce("x & y", "&") == "x <mark>&amp;</mark> y"
    assert realce("", "abc") == ""
