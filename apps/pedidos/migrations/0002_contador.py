from django.db import migrations


def criar_contador(apps, schema_editor):
    ContadorPedido = apps.get_model("pedidos", "ContadorPedido")
    ContadorPedido.objects.get_or_create(pk=1, defaults={"ultimo_numero": 0})


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0001_initial"),
    ]

    operations = [migrations.RunPython(criar_contador, migrations.RunPython.noop)]
