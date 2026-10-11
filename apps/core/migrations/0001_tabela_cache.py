from django.core.management import call_command
from django.db import migrations


def criar_tabela_cache(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = []
    operations = [migrations.RunPython(criar_tabela_cache, migrations.RunPython.noop)]
