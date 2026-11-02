"""AC-PLT-19 (RN-PLT-13, C-06): known ways around gitleaks do not get a secret past it (T-PLT-04).

Found in the review of ``3d50418`` and reproduced there with gitleaks v8.30.1. Marker ``gitleaks``
(Docker); each case runs the real hook ``entry`` and/or the real ``secrets`` steps (see
``gitleaks_support``). Fake secrets are generated at runtime.
"""

from __future__ import annotations

import gitleaks_support as gl
import pytest
from conftest import Scan

pytestmark = pytest.mark.gitleaks


def test_AC_PLT_19_inline_gitleaks_allow_does_not_hide_a_token(scan: Scan) -> None:
    # B-1: a `gitleaks:allow` comment on the line silences the finding unless
    # --ignore-gitleaks-allow is passed.
    token = gl.fake_github_token()
    result = scan(f"GITHUB_TOKEN={token}  # gitleaks:allow\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output
