"""Fail on a GitHub Actions configuration that breaks RN-PLT-18 (AC-PLT-33, design.md §3.5).

Usage (from the repo root, CI job ``lint``):
    python scripts/check_workflows.py [--root PATH]

Checks every ``.github/workflows/*.yml|*.yaml``, every ``.github/actions/**/action.yml|yaml`` (any
case) and every local action a ``uses: ./X`` reaches, wherever it lives:

- ``forbidden-trigger``: ``pull_request_target`` or ``workflow_run`` (they run with the base repo's
  privileges on code or artifacts a fork controls).
- ``permissions-missing`` / ``permissions-top-level``: the workflow has no top-level
  ``permissions``, or a scope there is not ``read``/``none`` (``read-all`` and ``{}`` pass).
- ``permissions-job``: a job asks for ``write`` (or ``write-all``) outside
  ``JOB_PERMISSION_ALLOWLIST``.
- ``secrets``: any use of the ``secrets`` context other than ``secrets.GITHUB_TOKEN``, and
  ``secrets: inherit``.
- ``uses-pin``: a remote ``uses:`` not pinned by a full 40-hex commit SHA (``docker://`` needs an
  ``@sha256:<64 hex>`` digest); ``uses-tag-comment``: a SHA pin without the tag in a comment on
  its own line (``# vX.Y.Z``, what Dependabot keeps updated).
- ``uses-local``: a ``uses: ./X`` that is not a plain path inside the repo, a step's without an
  ``action.yml``/``action.yaml`` there, or a job's that is not a file of ``.github/workflows/``.
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
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

FORBIDDEN_TRIGGERS = frozenset({"pull_request_target", "workflow_run"})
READ_LEVELS = frozenset({"read", "none"})
JOB_LEVELS = frozenset({"read", "write", "none"})
YAML_SUFFIXES = frozenset({".yml", ".yaml"})
ACTION_NAMES = frozenset({"action.yml", "action.yaml"})

# (workflow path relative to the repo, job id, scope) that may ask for `write`. Each entry needs a
# reason next to it and the reviewer's verdict (red zone). Empty in 00 (design.md §3.5).
JOB_PERMISSION_ALLOWLIST: frozenset[tuple[str, str, str]] = frozenset()

# Check names = required checks of the ruleset (design.md §6.3). A job is required if its id or
# its `name:` is one of them, or if its `name:` has an expression (it could render as any).
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
# What must follow a SHA-pinned `uses:` value on its line.
TAG_COMMENT = re.compile(r"[ \t]+#[ \t]*\S")
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


class _UsesRef(str):
    """A ``uses:`` value with the rest of its own line after it (where the tag comment goes)."""

    tail = ""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys (PyYAML keeps the last one silently) and keeps, for
    every ``uses:`` value, what follows it on its line."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=True)
            if key in seen:  # an unhashable key raises TypeError: caught as invalid-yaml
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        mapping = super().construct_mapping(node, deep=deep)
        for key_node, value_node in node.value:
            if key_node.value == "uses" and isinstance(mapping.get("uses"), str):
                ref = _UsesRef(mapping["uses"])
                end = value_node.end_mark
                if isinstance(end.buffer, str):
                    newline = end.buffer.find("\n", end.pointer)
                    ref.tail = end.buffer[end.pointer : newline if newline >= 0 else None]
                mapping["uses"] = ref
        return mapping


def _is_workflow(root: Path, path: Path) -> bool:
    return path.parent == root / ".github" / "workflows"


def find_files(root: Path) -> list[Path]:
    """Workflows and actions found by location; extensions and file names in any case."""
    github = root / ".github"
    workflows = [p for p in (github / "workflows").glob("*") if p.suffix.lower() in YAML_SUFFIXES]
    actions = [p for p in (github / "actions").glob("**/*") if p.name.lower() in ACTION_NAMES]
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


def check_uses(ref: Any) -> list[tuple[str, str]]:
    """(rule, detail) for one remote ``uses:`` value (local ones go through ``resolve_local``)."""
    if not isinstance(ref, str):
        return [("uses-pin", f"uses is not a string: {ref!r}")]
    if ref.startswith("docker://"):
        if PINNED_DOCKER.fullmatch(ref):
            return []
        return [("uses-pin", f"{ref!r} is not pinned by an @sha256:<64 hex> digest")]
    if not PINNED_ACTION.fullmatch(ref):
        return [("uses-pin", f"{ref!r} is not pinned by a full 40-hex commit SHA")]
    if not TAG_COMMENT.match(getattr(ref, "tail", "")):
        return [("uses-tag-comment", f"{ref!r} has no '# <tag>' comment on its line")]
    return []


def resolve_local(root: Path, ref: str, job_level: bool) -> tuple[list[Path], str | None]:
    """Action files a local ``uses: ./X`` runs, or why it fails closed (rule ``uses-local``).

    A job's ``uses:`` is a reusable workflow: a file of ``.github/workflows/``, checked there. A
    step's is an action directory relative to the workspace: its ``action.y(a)ml`` is checked
    wherever it lives, not only under ``.github/actions/``.
    """
    parts = PurePosixPath(ref[2:]).parts
    target = root.joinpath(*parts)
    if "@" in ref or "\\" in ref or ".." in parts or not target.resolve().is_relative_to(root):
        return [], f"{ref!r} is not a plain path inside the repo"
    if job_level:
        workflow = target.is_file() and _is_workflow(root, target)
        if workflow and target.suffix.lower() in YAML_SUFFIXES:
            return [], None
        return [], f"reusable workflow {ref!r} is not a file of .github/workflows/"
    found = []
    if target.is_dir():
        found = sorted(p for p in target.iterdir() if p.name.lower() in ACTION_NAMES)
    if not found:
        return [], f"local action {ref!r} has no action.yml/action.yaml"
    return found, None


def _triggers(workflow: dict[Any, Any]) -> tuple[list[str], str | None]:
    """Event names of ``on`` (PyYAML reads the bare key as ``True``), or an error."""
    keys = [k for k in ("on", True) if k in workflow]
    if len(keys) != 1:
        return [], "needs exactly one 'on' key"
    on = workflow[keys[0]]
    if isinstance(on, str):
        return [on], None
    if isinstance(on, list | dict) and all(isinstance(e, str) for e in on):
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


def _is_required(job_id: Any, name: Any) -> bool:
    if isinstance(name, str) and ("${{" in name or name in REQUIRED_CHECKS):
        return True
    return isinstance(job_id, str) and job_id in REQUIRED_CHECKS


# Local `uses: ./X` found while checking a file: (ref, job-level?, where, for the message).
LocalRefs = list[tuple[str, bool, str]]


def check_workflow(rel_path: str, workflow: Any, local: LocalRefs) -> list[Violation]:
    if not isinstance(workflow, dict):
        return [Violation(rel_path, "invalid-workflow", "the file is not a YAML mapping")]
    out: list[Violation] = []

    def add(rule: str, detail: str) -> None:
        out.append(Violation(rel_path, rule, detail))

    events, error = _triggers(workflow)
    if error:
        add("invalid-workflow", error)
    for event in events:
        if event.lower() in FORBIDDEN_TRIGGERS:
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
        inherit = job.get("secrets")
        if isinstance(inherit, str) and inherit.strip().lower() == "inherit":
            add("secrets", f"job {job_id!r}: 'secrets: inherit' passes every secret")
        if "if" in job and _is_required(job_id, job.get("name")):
            add("job-if", f"job {job_id!r}: job-level if: on a required check")
        refs = [(job["uses"], True)] if "uses" in job else []
        refs += [(s["uses"], False) for s in _steps(job) if isinstance(s, dict) and "uses" in s]
        for ref, job_level in refs:
            if isinstance(ref, str) and ref.startswith("./"):
                local.append((ref, job_level, f"job {job_id!r}"))
                continue
            for rule, detail in check_uses(ref):
                add(rule, f"job {job_id!r}: {detail}")

    for detail in check_secrets(workflow):
        add("secrets", detail)
    return out


def check_action(rel_path: str, action: Any, local: LocalRefs) -> list[Violation]:
    if not isinstance(action, dict) or not isinstance(action.get("runs"), dict):
        return [Violation(rel_path, "invalid-workflow", "action without a 'runs' mapping")]
    runs = action["runs"]
    refs = [step["uses"] for step in _steps(runs) if isinstance(step, dict) and "uses" in step]
    image = runs.get("image")
    if isinstance(image, str) and image.startswith("docker://"):
        refs.append(image)
    out = []
    for ref in refs:
        if isinstance(ref, str) and ref.startswith("./"):
            local.append((ref, False, "step"))
            continue
        out += [Violation(rel_path, rule, detail) for rule, detail in check_uses(ref)]
    out += [Violation(rel_path, "secrets", detail) for detail in check_secrets(action)]
    return out


def check_file(root: Path, path: Path, local: LocalRefs) -> list[Violation]:
    rel_path = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
        document = yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass
    except (yaml.YAMLError, UnicodeDecodeError, TypeError) as exc:
        return [Violation(rel_path, "invalid-yaml", " ".join(str(exc).split()))]
    if _is_workflow(root, path):
        return check_workflow(rel_path, document, local)
    return check_action(rel_path, document, local)


def scan(root: Path) -> tuple[list[Violation], list[Path]]:
    """Violations and every file checked: the ones found plus the local actions they reach."""
    root = root.resolve()
    queue = find_files(root)
    if not any(_is_workflow(root, path) for path in queue):
        return [Violation(".github/workflows", "no-workflows", "no workflow found to check")], []
    seen = {path.resolve() for path in queue}
    checked: list[Path] = []
    out: list[Violation] = []
    while queue:
        path = queue.pop(0)
        checked.append(path)
        local: LocalRefs = []
        out += check_file(root, path, local)
        rel_path = path.relative_to(root).as_posix()
        for ref, job_level, where in local:
            targets, error = resolve_local(root, ref, job_level)
            if error:
                out.append(Violation(rel_path, "uses-local", f"{where}: {error}"))
            for target in targets:
                if target.resolve() not in seen:
                    seen.add(target.resolve())
                    queue.append(target)
    return out, checked


def check_repo(root: Path) -> list[Violation]:
    return scan(root)[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check GitHub Actions config (RN-PLT-18).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    violations, checked = scan(args.root)
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        return 1
    print(f"check_workflows: {len(checked)} files OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
