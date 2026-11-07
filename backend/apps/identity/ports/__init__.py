"""What identity needs from SPEC-02 and SPEC-10, as Protocols resolved by settings (design.md §6.4).

Services call ``registry``. Nothing here imports ``apps.tenancy`` nor ``apps.audit``; they import
these modules to implement the Protocols.
"""
