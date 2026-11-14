"""``tenant_probe``: a stand-in business module for the tenant base (SPEC-02 design.md §9).

``Widget(TenantModel)`` lets the tests of ``apps.common.tenancy`` (T-TEN-03), the request
resolution and the cross-tenant suite (T-TEN-08, T-TEN-09) and the per-organization tasks
(T-TEN-11) run on a real tenant table before 04 or 06 bring theirs. Its views and tasks arrive with
those tasks.
"""
