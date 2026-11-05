"""Static checks on the project's migration files (design.md §3.2.7, RN-PLT-10).

``rules`` holds the checks on one migration; ``manage.py lint_migrations`` runs them on every
migration of the ``apps.*`` packages (CI job ``migrations``, step 8).
"""
