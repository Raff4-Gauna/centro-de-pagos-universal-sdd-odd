# Synthetic (T-PLT-24): RunPython without reverse_code, rejected. The last migration, so the round
# trip fails on it first (Django's IrreversibleError, before touching the database).

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def seed_items(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Item = apps.get_model("bad_irreversible", "Item")
    Item.objects.get_or_create(name="seed")


class Migration(migrations.Migration):
    dependencies = [
        ("bad_irreversible", "0003_lowercase_item_names"),
    ]

    operations = [
        migrations.RunPython(seed_items),
    ]
