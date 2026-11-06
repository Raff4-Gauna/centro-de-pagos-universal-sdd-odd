# Synthetic (T-PLT-24): data only; RunPython.noop is its reverse (0002 drops the column anyway).

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def fill_codes(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Part = apps.get_model("good_reversible", "Part")
    for part in Part.objects.filter(code=""):
        part.code = part.name.upper()
        part.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [
        ("good_reversible", "0002_part_code"),
    ]

    operations = [
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
    ]
