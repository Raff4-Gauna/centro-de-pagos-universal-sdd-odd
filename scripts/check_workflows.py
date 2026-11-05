"""Fail on a GitHub Actions configuration that breaks RN-PLT-18 (AC-PLT-33, design.md §3.5).

Usage (from the repo root, CI job ``lint``):
    python scripts/check_workflows.py [--root PATH]

Checks every ``.github/workflows/*.yml|*.yaml`` and every ``.github/actions/**/action.yml|yaml``:

- ``forbidden-trigger``: ``pull_request_target`` or ``workflow_run`` (they run with the base repo's
  privileges on code or artifacts a fork controls).
- ``permissions-missing`` / ``permissions-top-level``: the workflow has no top-level
  ``permissions``, or a scope there is not ``read``/``none`` (``read-all`` and ``{}`` pass).
- ``permissions-job``: a job asks for ``write`` (or ``write-all``) outside
  ``JOB_PERMISSION_ALLOWLIST``.
- ``secrets``: any use of the ``secrets`` context other than ``secrets.GITHUB_TOKEN``, and
  ``secrets: inherit``.
- ``uses-pin``: a remote ``uses:`` not pinned by a full 40-hex commit SHA (``docker://`` needs an
  ``@sha256:<64 hex>`` digest); ``uses-tag-comment``: a SHA pin without the tag in a comment
  (``# vX.Y.Z``, what Dependabot keeps updated).
- ``job-if``: a job-level ``if:`` on a required check (a skipped required check counts as passed).
- ``invalid-yaml`` / ``invalid-workflow`` / ``no-workflows``: fail closed on what cannot be read.

Each violation is printed on stderr as ``<path>: [<rule>] <detail>``. Exit 0 ok, 1 violations.
Needs PyYAML (backend env); everything else is stdlib.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Hashable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FORBIDDEN_TRIGGERS = frozenset({"pull_request_target", "workflow_run"})
READ_LEVELS = frozenset({"read", "none"})
JOB_LEVELS = frozenset({"read", "write", "none"})

# (workflow path relative to the repo, job id, scope) that may ask for `write`. Each entry needs a
# reason next to it and the reviewer's verdict (red zone). Empty in 00 (design.md §3.5).
JOB_PERMISSION_ALLOWLIST: frozenset[tuple[str, str, str]] = frozenset()

# Check names = required checks of the ruleset (design.md §6.3). A job is required if its id or
# its `name:` is one of them.
REQUIRED_CHECKS = frozenset(
    {
        "lint",
        "file-size",
        "secrets",
        "deps-audit",
        "typecheck",
        "architecture",
        "tests",
        "coverage",
        "migrations",
        "build",
        "zona-roja",
    }
)

PINNED_ACTION = re.compile(r"[^@\s]+@[0-9a-f]{40}")
PINNED_DOCKER = re.compile(r"docker://[^@\s]+@sha256:[0-9a-f]{64}")
EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
# A string literal (skipped, so `'no secrets'` is not a use) or the `secrets` context with what
# follows it. Expressions are case-insensitive; `needs.secrets` (a job named secrets) is not it.
SECRETS_USE = re.compile(
    r"'(?:[^']|'')*'"
    r"|(?<![\w.\-])secrets(?![\w\-])"
    r"(?:\s*\.\s*(?P<dot>[A-Za-z_][\w\-]*)|\s*\[\s*'(?P<bracket>(?:[^']|'')*)'\s*\])?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.rule}] {self.detail}"


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys (PyYAML keeps the last one silently)."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def find_files(root: Path) -> list[Path]:
    github = root / ".github"
    workflows = [p for p in (github / "workflows").glob("*") if p.suffix in {".yml", ".yaml"}]
    actions = [
        p for p in (github / "actions").glob("**/*") if p.name in {"action.yml", "action.yaml"}
    ]
    return sorted(p for p in workflows + actions if p.is_file())


def _walk(node: Any, key: Any = None) -> Iterator[tuple[Any, str]]:
    """Every string (keys included) with the key it sits under."""
    if isinstance(node, dict):
        for k, value in node.items():
            if isinstance(k, str):
                yield None, k
            yield from _walk(value, k)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, key)
    elif isinstance(node, str):
        yield key, node


def _expressions(key: Any, text: str) -> list[str]:
    found = EXPRESSION.findall(text)
    # `if:` is an expression even without `${{ }}`.
    if key == "if" and not found:
        found = [text]
    return found


def check_secrets(document: Any) -> list[str]:
    problems = []
    for key, text in _walk(document):
        for expression in _expressions(key, text):
            for match in SECRETS_USE.finditer(expression):
                if match.group(0).startswith("'"):
                    continue
                name = match.group("dot") or match.group("bracket")
                if name is None or name.upper() != "GITHUB_TOKEN":
                    problems.append(f"secrets context other than GITHUB_TOKEN: {match.group(0)!r}")
    return problems


def _steps(owner: Any) -> list[Any]:
    steps = owner.get("steps", []) if isinstance(owner, dict) else []
    return steps if isinstance(steps, list) else []


def check_uses(ref: Any, text: str) -> list[tuple[str, str]]:
    """(rule, detail) for one `uses:` value; ``text`` is the raw file, for the tag comment."""
    if not isinstance(ref, str):
        return [("uses-pin", f"uses is not a string: {ref!r}")]
    if ref.startswith("./"):
        return []
    if ref.startswith("docker://"):
        if PINNED_DOCKER.fullmatch(ref):
            return []
        return [("uses-pin", f"{ref!r} is not pinned by an @sha256:<64 hex> digest")]
    if not PINNED_ACTION.fullmatch(ref):
        return [("uses-pin", f"{ref!r} is not pinned by a full 40-hex commit SHA")]
    comment = re.compile(r"uses:\s*([\"']?)" + re.escape(ref) + r"\1[ \t]+#[ \t]*\S")
    if not comment.search(text):
        return [("uses-tag-comment", f"{ref!r} has no '# <tag>' comment on its line")]
    return []


def _triggers(workflow: dict[Any, Any]) -> tuple[list[str], str | None]:
    """Event names of ``on`` (PyYAML reads the bare key as ``True``), or an error."""
    keys = [k for k in ("on", True) if k in workflow]
    if len(keys) != 1:
        return [], "needs exactly one 'on' key"
    on = workflow[keys[0]]
    if isinstance(on, str):
        return [on], None
    if isinstance(on, list) and all(isinstance(e, str) for e in on):
        return list(on), None
    if isinstance(on, dict) and all(isinstance(e, str) for e in on):
        return list(on), None
    return [], f"unreadable 'on': {on!r}"


def check_top_permissions(permissions: Any) -> list[str]:
    if permissions == "read-all" or permissions == {}:
        return []
    if not isinstance(permissions, dict):
        return [f"top-level permissions {permissions!r} is not read-only"]
    return [
        f"scope {scope!r} is {level!r} (only read/none)"
        for scope, level in permissions.items()
        if level not in READ_LEVELS
    ]


def check_job_permissions(rel_path: str, job_id: str, permissions: Any) -> list[str]:
    if permissions in ("read-all", {}):
        return []
    if not isinstance(permissions, dict):
        return [f"job {job_id!r}: permissions {permissions!r} (write-all or invalid)"]
    problems = []
    for scope, level in permissions.items():
        if level not in JOB_LEVELS:
            problems.append(f"job {job_id!r}: scope {scope!r} has invalid level {level!r}")
        elif level == "write" and (rel_path, job_id, scope) not in JOB_PERMISSION_ALLOWLIST:
            problems.append(f"job {job_id!r}: scope {scope!r} is write, not in the allowlist")
    return problems


def check_workflow(rel_path: str, workflow: Any, text: str) -> list[Violation]:
    if not isinstance(workflow, dict):
        return [Violation(rel_path, "invalid-workflow", "the file is not a YAML mapping")]
    out: list[Violation] = []

    def add(rule: str, detail: str) -> None:
        out.append(Violation(rel_path, rule, detail))

    events, error = _triggers(workflow)
    if error:
        add("invalid-workflow", error)
    for event in events:
        if event in FORBIDDEN_TRIGGERS:
            add("forbidden-trigger", f"trigger {event!r} is never allowed (RN-PLT-18)")

    if "permissions" not in workflow:
        add("permissions-missing", "no top-level permissions: the token gets the repo default")
    else:
        for detail in check_top_permissions(workflow["permissions"]):
            add("permissions-top-level", detail)

    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        add("invalid-workflow", "'jobs' is missing or not a non-empty mapping")
        jobs = {}
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            add("invalid-workflow", f"job {job_id!r} is not a mapping")
            continue
        if "permissions" in job:
            for detail in check_job_permissions(rel_path, str(job_id), job["permissions"]):
                add("permissions-job", detail)
        if job.get("secrets") == "inherit":
            add("secrets", f"job {job_id!r}: 'secrets: inherit' passes every secret")
        if "if" in job and {job_id, job.get("name")} & REQUIRED_CHECKS:
            add("job-if", f"job {job_id!r}: job-level if: on a required check")
        refs = [job["uses"]] if "uses" in job else []
        refs += [step["uses"] for step in _steps(job) if isinstance(step, dict) and "uses" in step]
        for ref in refs:
            for rule, detail in check_uses(ref, text):
                add(rule, f"job {job_id!r}: {detail}")

    for detail in check_secrets(workflow):
        add("secrets", detail)
    return out


def check_action(rel_path: str, action: Any, text: str) -> list[Violation]:
    if not isinstance(action, dict) or not isinstance(action.get("runs"), dict):
        return [Violation(rel_path, "invalid-workflow", "action without a 'runs' mapping")]
    runs = action["runs"]
    refs = [step["uses"] for step in _steps(runs) if isinstance(step, dict) and "uses" in step]
    image = runs.get("image")
    if isinstance(image, str) and image.startswith("docker://"):
        refs.append(image)
    out = [
        Violation(rel_path, rule, detail) for ref in refs for rule, detail in check_uses(ref, text)
    ]
    out += [Violation(rel_path, "secrets", detail) for detail in check_secrets(action)]
    return out


def check_file(root: Path, path: Path) -> list[Violation]:
    rel_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    try:
        document = yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as exc:
        return [Violation(rel_path, "invalid-yaml", " ".join(str(exc).split()))]
    if path.parent.name == "workflows" and path.parent.parent.name == ".github":
        return check_workflow(rel_path, document, text)
    return check_action(rel_path, document, text)


def check_repo(root: Path) -> list[Violation]:
    files = find_files(root)
    if not any(path.parent.name == "workflows" for path in files):
        return [Violation(".github/workflows", "no-workflows", "no workflow found to check")]
    return [violation for path in files for violation in check_file(root, path)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check GitHub Actions config (RN-PLT-18).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    violations = check_repo(root)
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        return 1
    print(f"check_workflows: {len(find_files(root))} files OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
