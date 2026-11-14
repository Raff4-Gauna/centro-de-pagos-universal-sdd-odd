"""``summarize_user_agent`` (RN-IDA-24, RNF-IDA-05): the browser and the OS, nothing more."""

from __future__ import annotations

import pytest

from apps.identity.domain.client_hint import ClientHint, summarize_user_agent

CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
EDGE_WINDOWS = CHROME_WINDOWS + " Edg/131.0.2903.86"
OPERA_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36 OPR/116.0.0.0"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"
SAFARI_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.1 Safari/605.1.15"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
)
CHROME_IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1"
)
FIREFOX_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) FxiOS/133.0 Mobile/15E148 Safari/605.1.15"
)
SAMSUNG_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36"
)
CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Mobile Safari/537.36"
)
CHROME_OS = (
    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@pytest.mark.parametrize(
    ("user_agent", "browser", "os"),
    [
        (CHROME_WINDOWS, "Chrome", "Windows"),
        (EDGE_WINDOWS, "Edge", "Windows"),
        (OPERA_MAC, "Opera", "macOS"),
        (FIREFOX_LINUX, "Firefox", "Linux"),
        (SAFARI_MAC, "Safari", "macOS"),
        (SAFARI_IPHONE, "Safari", "iOS"),
        (CHROME_IPAD, "Chrome", "iOS"),
        (FIREFOX_IPHONE, "Firefox", "iOS"),
        (SAMSUNG_ANDROID, "Samsung Internet", "Android"),
        (CHROME_ANDROID, "Chrome", "Android"),
        (CHROME_OS, "Chrome", "ChromeOS"),
    ],
)
def test_RN_IDA_24_summarizes_browser_and_os(user_agent: str, browser: str, os: str) -> None:
    assert summarize_user_agent(user_agent) == ClientHint(browser=browser, os=os)


@pytest.mark.parametrize("user_agent", [None, "", "curl/8.5.0", "x" * 4096, "\x00\n"])
def test_RN_IDA_24_unknown_agent_is_empty(user_agent: str | None) -> None:
    assert summarize_user_agent(user_agent) == ClientHint(browser="", os="")


def test_RNF_IDA_05_no_version_nor_device_survives() -> None:
    hint = summarize_user_agent(SAMSUNG_ANDROID)
    # Only names from a closed list: no version, model or build that would narrow the device.
    for fragment in ("14", "SM-S918B", "26.0", "122"):
        assert fragment not in hint.browser
        assert fragment not in hint.os
