# Synthetic (T-PLT-24): RunSQL with its reverse_sql, nested in SeparateDatabaseAndState.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("good_reversible", "0003_fill_part_codes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="CREATE INDEX good_reversible_part_code_idx ON good_reversible_part (code)",
                    reverse_sql="DROP INDEX good_reversible_part_code_idx",
                ),
            ],
        ),
    ]
