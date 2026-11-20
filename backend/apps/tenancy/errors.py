"""Errors of SPEC-02's own rules that more than one service raises (design.md §3.2, §6).

``InvalidTransition`` is ``409 invalid_transition`` (C-05): a change of state the entity does not
admit from the state it is in (reactivating an active branch, deactivating an inactive one; later,
revoking an accepted invitation or changing the role of a revoked membership). The service emits
``transition.rejected`` before raising it, outside its transaction (design.md §3.3, AC-TEN-37).
The ``detail`` is fixed: it never names the entity nor repeats the input.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException


class InvalidTransition(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invalid_transition"
    default_detail = "La acción no corresponde al estado actual."
