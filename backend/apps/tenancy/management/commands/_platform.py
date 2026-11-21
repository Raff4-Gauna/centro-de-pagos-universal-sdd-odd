"""What the operator's commands of ``apps.tenancy`` share: exit codes, ``--org`` and ``--operator``.

``1`` is a refusal with nothing changed and ``2`` a bad argument (argparse's own code), as in
``tenancy_create_org``. ``operator_of`` checks ``--operator`` against ``PLATFORM_OPERATOR_EMAILS``
(``apps.common.platform_operators``) and names the OS user next to it; a refusal never repeats the
value.
"""

from __future__ import annotations

import uuid

from django.core.management.base import CommandError

from apps.common.platform_operators import OperatorNotAllowedError, allowed_operator, os_user
from apps.tenancy.services.platform_org import Operator

REFUSED_EXIT = 1
USAGE_EXIT = 2
OPERATOR_HELP = "Your email in PLATFORM_OPERATOR_EMAILS; audited with the OS user."
ORG_HELP = "Id (UUID) of the organization."


def operator_of(value: object) -> Operator:
    try:
        return Operator(email=allowed_operator(value), os_user=os_user())
    except OperatorNotAllowedError as error:
        raise CommandError(str(error), returncode=USAGE_EXIT) from None


def organization_id(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        raise CommandError(
            "--org must be the id (UUID) of an organization", returncode=USAGE_EXIT
        ) from None
