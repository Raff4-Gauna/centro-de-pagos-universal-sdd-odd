"""A User-Agent summarized to its browser and OS (RN-IDA-24, RNF-IDA-05, design.md §7.7). Pure.

"Seguridad" shows each session as "Chrome en Windows": that is all a person needs to recognise a
device, and all that is kept. The raw User-Agent is never stored nor logged: versions, device
models and builds narrow a device down, so only a name from the closed lists below survives. An
agent none of them names is ``""`` (the screen says it does not know), never a guess.

The order of each list matters: Edge, Opera and Samsung Internet also say ``Chrome/``; Chrome also
says ``Safari/``; an iPhone says ``like Mac OS X`` and Android says ``Linux``. Only the first
``MAX_SCANNED_LENGTH`` characters are read, the most the BFF relays.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_SCANNED_LENGTH = 512

# (marker, name): the first marker found in the agent names it.
_BROWSERS: tuple[tuple[str, str], ...] = (
    ("Edg/", "Edge"),
    ("EdgiOS/", "Edge"),
    ("EdgA/", "Edge"),
    ("OPR/", "Opera"),
    ("SamsungBrowser/", "Samsung Internet"),
    ("Firefox/", "Firefox"),
    ("FxiOS/", "Firefox"),
    ("CriOS/", "Chrome"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
_SYSTEMS: tuple[tuple[str, str], ...] = (
    ("Windows NT", "Windows"),
    ("iPhone", "iOS"),
    ("iPad", "iOS"),
    ("iPod", "iOS"),
    ("Android", "Android"),
    ("CrOS", "ChromeOS"),
    ("Macintosh", "macOS"),
    ("Mac OS X", "macOS"),
    ("Linux", "Linux"),
)


@dataclass(frozen=True, slots=True)
class ClientHint:
    browser: str
    os: str


def _first(agent: str, table: tuple[tuple[str, str], ...]) -> str:
    return next((name for marker, name in table if marker in agent), "")


def summarize_user_agent(user_agent: str | None) -> ClientHint:
    """The browser and OS named in ``user_agent``; ``""`` for whichever it does not name."""
    agent = (user_agent or "")[:MAX_SCANNED_LENGTH]
    return ClientHint(browser=_first(agent, _BROWSERS), os=_first(agent, _SYSTEMS))
