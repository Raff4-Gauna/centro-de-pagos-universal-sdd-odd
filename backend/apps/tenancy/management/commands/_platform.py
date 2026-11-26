"""What the operator's commands of ``apps.tenancy`` share: exit codes, ``--org`` and ``--operator``.

``1`` is a refusal with nothing changed and ``2`` a bad argument (argparse's own code), as in
``tenancy_create_org``. ``operator_of`` checks ``--operator`` against ``PLATFORM_OPERATOR_EMAILS``
(``apps.common.platform_operators``) and names the OS user next to it; a refusal never repeats the
value. Before that exit ``2`` it writes one WARNING ``tenancy.platform_operator_refused`` in the
application log with the command and the OS user only (Q-241), through ``checked_operator``, the
check every operator command shares (Q-242): it is not an audit event of any company, and neither
the email nor the value of ``--operator`` is logged (C-06, RNF-IDA-05).
"""

from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.common.platform_operators import OperatorNotAllowedError, checked_operator, os_user
from apps.tenancy.services.platform_org import Operator

REFUSED_EXIT = 1
USAGE_EXIT = 2
OPERATOR_HELP = "Your email in PLATFORM_OPERATOR_EMAILS; audited with the OS user."
ORG_HELP = "Id (UUID) of the organization."
OPERATOR_REFUSED_EVENT = "tenancy.platform_operator_refused"


def command_name(command: BaseCommand) -> str:
    """The name ``manage.py`` runs ``command`` by: the last part of its module."""
    return type(command).__module__.rpartition(".")[2]


def operator_of(value: object, command: BaseCommand) -> Operator:
    try:
        email = checked_operator(value, event=OPERATOR_REFUSED_EVENT, command=command_name(command))
    except OperatorNotAllowedError as error:
        raise CommandError(str(error), returncode=USAGE_EXIT) from None
    return Operator(email=email, os_user=os_user())


def organization_id(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        raise CommandError(
            "--org must be the id (UUID) of an organization", returncode=USAGE_EXIT
        ) from None
