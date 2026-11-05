# Synthetic (T-PLT-24): RunSQL without reverse_sql nested in SeparateDatabaseAndState, rejected.
# Django only checks `reversible` at the top level: reverting this would fail mid-way.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("bad_irreversible", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "CREATE INDEX bad_irreversible_item_name_idx ON bad_irreversible_item (name)"
                ),
            ],
        ),
    ]
