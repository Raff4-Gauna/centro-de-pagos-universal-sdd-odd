# Synthetic (T-PLT-24): RunSQL without reverse_sql, rejected.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("bad_irreversible", "0002_item_name_index"),
    ]

    operations = [
        migrations.RunSQL("UPDATE bad_irreversible_item SET name = lower(name)"),
    ]
