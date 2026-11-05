# Synthetic (T-PLT-23): a data-only migration (RunPython with its reverse), accepted.

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def fill_slugs(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Gizmo = apps.get_model("bad_mixed", "Gizmo")
    for gizmo in Gizmo.objects.filter(slug=""):
        gizmo.slug = gizmo.name.lower()
        gizmo.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("bad_mixed", "0002_add_slug_and_backfill"),
    ]

    operations = [
        migrations.RunPython(fill_slugs, migrations.RunPython.noop),
    ]
