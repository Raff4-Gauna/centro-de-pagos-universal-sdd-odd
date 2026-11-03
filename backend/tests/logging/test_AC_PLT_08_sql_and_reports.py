"""AC-PLT-08 (RN-PLT-06, C-06): SQL parameters and URI settings never reach a log or a report.

T-PLT-12 review, taken by T-PLT-14: with ``DEBUG`` and ``LOG_LEVEL=DEBUG``, ``django.db.backends``
logs every query with its parameters (message and ``extra``), so it is held at INFO whatever the
root level; its ERRORs (``on_commit`` failures) still go out. N-5: the error report and debug page
hide settings and ``request.META`` keys ending in ``URI`` too, like ``URL``, ``LOCATION``, ``DSN``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator

import pytest
from django.conf import settings
from django.db import connection
from django.test import RequestFactory
from django.views.debug import ExceptionReporter
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common.logging import get_logger
from apps.common.logging.setup import configure_logging, logging_config
from tests.logging.conftest import StdoutLog

PASSWORD = "sql-sentinel-" + "4c18"
REPORT_HOST = "broker.example"
# Module constant: the error report shows the source around each frame.
URI_WITH_PASSWORD = "amqp://hub:" + PASSWORD + "@" + REPORT_HOST + ":5672/hub"


@pytest.fixture
def debug_level() -> Iterator[None]:
    configure_logging(logging_config("DEBUG"))
    yield
    configure_logging(settings.LOGGING)


def test_AC_PLT_08_sql_debug_log_is_never_emitted(debug_level: None, stdout_log: StdoutLog) -> None:
    # The same call django/db/backends/utils.py makes for each query.
    logging.getLogger("django.db.backends").debug(
        "(%.3f) %s; args=%s; alias=%s",
        0.001,
        "INSERT INTO t VALUES (%s)",
        (PASSWORD,),
        "default",
        extra={"sql": "SELECT " + repr(PASSWORD), "params": (PASSWORD,)},  # the rendered SQL
    )
    logging.getLogger("django.db.backends.schema").debug("ALTER %s", PASSWORD)
    get_logger("apps.demo").debug("demo.debug_still_shown")
    logging.getLogger("django.db.backends.base").error("demo.db_error_still_shown")
    log = stdout_log.read()
    assert PASSWORD not in log.out + log.err
    messages = [event["message"] for event in log.events]
    assert messages == ["demo.debug_still_shown", "demo.db_error_still_shown"]


@pytest.mark.integration
@pytest.mark.django_db
def test_AC_PLT_08_real_query_parameters_never_logged(
    debug_level: None, stdout_log: StdoutLog
) -> None:
    connection.force_debug_cursor = True  # what DEBUG=true does
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s", [PASSWORD])
            assert cursor.fetchone() == (PASSWORD,)
    finally:
        connection.force_debug_cursor = False
    assert connection.queries  # the query was recorded, so it would have been logged
    log = stdout_log.read()
    assert PASSWORD not in log.out + log.err


def test_C_06_error_report_hides_uri_settings_and_meta(settings: SettingsWrapper) -> None:
    settings.CELERY_RESULT_BACKEND_URI = URI_WITH_PASSWORD
    request = RequestFactory().get("/", BROKER_URI=URI_WITH_PASSWORD)
    try:
        raise RuntimeError("demo")
    except RuntimeError:
        reporter = ExceptionReporter(request, *sys.exc_info())
        report = reporter.get_traceback_text() + reporter.get_traceback_html()
    assert "CELERY_RESULT_BACKEND_URI" in report  # the key is shown, its value is not
    assert REPORT_HOST not in report
    assert PASSWORD not in report
