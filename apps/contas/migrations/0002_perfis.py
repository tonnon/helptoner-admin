from django.db import migrations

PERFIS = ("Administrador", "Vendedor")


def criar_perfis(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nome in PERFIS:
        Group.objects.get_or_create(name=nome)


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(criar_perfis, migrations.RunPython.noop)]
