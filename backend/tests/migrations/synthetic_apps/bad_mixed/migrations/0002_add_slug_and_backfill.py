# Synthetic (T-PLT-23): schema (AddField) and data (RunPython) in one migration, rejected.

from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def fill_slugs(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Gizmo = apps.get_model("bad_mixed", "Gizmo")
    for gizmo in Gizmo.objects.filter(slug=""):
        gizmo.slug = gizmo.name.lower()
        gizmo.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("bad_mixed", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="gizmo",
            name="slug",
            field=models.SlugField(default=""),
        ),
        migrations.RunPython(fill_slugs, migrations.RunPython.noop),
    ]
