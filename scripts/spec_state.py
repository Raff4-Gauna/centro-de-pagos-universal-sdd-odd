"""Library behind ``check_spec_state.py``: parse the board and compare it with git and tests.

The CLI lives in ``check_spec_state.py``; this module holds the parsing and the rules so both stay
under the 400-line limit (``C-14``). Stdlib only.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

STATUS_ORDER = ("☐", "🔄", "🟡", "✅", "🧪", "⛔")
MERGED = frozenset({"✅", "🧪"})
PENDING = frozenset({"☐", "🔄", "🟡"})
BLOCKED = "⛔"
FINAL_STATES = frozenset({"Implemented", "Verified"})

TASK_RE = re.compile(r"\bT-[A-Z]+-\d+\b")
AC_RE = re.compile(r"\bAC-[A-Z]+-\d+\b")
PR_RE = re.compile(r"#(\d+)")
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
Q_RE = re.compile(r"\bQ-\d+\b")
HEADING = "## Resumen"
BEGIN = "<!-- check_spec_state:begin -->"
END = "<!-- check_spec_state:end -->"

TEST_PATTERNS = (
    "backend/tests/**/test_*.py",
    "scripts/tests/**/test_*.py",
    "frontend/src/**/*.test.ts",
    "frontend/src/**/*.test.tsx",
)
DEFAULT_BASELINE = Path(__file__).with_name("spec_state_baseline.json")


class StateError(Exception):
    """Invalid input: missing file, unknown spec, malformed table or git failure."""


@dataclass(frozen=True)
class Commit:
    sha: str
    pr: str
    subject: str


@dataclass(frozen=True)
class TaskRow:
    task_id: str
    status: str
    evidence: str
    acs: tuple[str, ...]
    line: int


@dataclass
class SpecResult:
    module: str
    tasks: list[TaskRow]
    acs: set[str]
    missing: list[str]
    allowed_missing: set[str]
    drift: list[str]


def load_baseline(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"baseline ilegible {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise StateError(f"baseline inválido (se esperaba un objeto): {path}")
    return data


def allowed_missing(baseline: dict[str, object], module: str) -> set[str]:
    entry = baseline.get(module)
    if not isinstance(entry, dict):
        return set()
    raw = entry.get("allow_missing_tests", [])
    if not isinstance(raw, list):
        raise StateError(f"baseline {module}: allow_missing_tests debe ser una lista")
    return {item for item in raw if isinstance(item, str)}


def discover_specs(root: Path, wanted: str | None) -> list[Path]:
    specs = sorted(
        path.parent
        for path in root.glob("specs/*/spec.sdd.md")
        if not path.parent.name.startswith("_")
    )
    if wanted:
        specs = [
            path for path in specs if path.name == wanted or path.name.startswith(f"{wanted}-")
        ]
        if not specs:
            raise StateError(f"no existe specs/{wanted}/*/spec.sdd.md")
    if not specs:
        raise StateError(f"no hay specs en {root / 'specs'}")
    return specs


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_status(cell: str) -> str:
    return next((symbol for symbol in STATUS_ORDER if symbol in cell), "?")


def read_tasks(path: Path) -> list[TaskRow]:
    if not path.is_file():
        raise StateError(f"falta {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(HEADING)
    except ValueError as exc:
        raise StateError(f"{path}: falta la sección '{HEADING}'") from exc

    table: list[tuple[int, str]] = []
    for number, line in enumerate(lines[start + 1 :], start=start + 2):
        if line.startswith("|"):
            table.append((number, line))
        elif table:
            break
    if len(table) < 2:
        raise StateError(f"{path}: la tabla de '{HEADING}' está vacía")

    header = split_row(table[0][1])
    try:
        index = {name: header.index(name) for name in ("ID", "AC", "Estado")}
    except ValueError as exc:
        raise StateError(f"{path}: faltan columnas ID/AC/Estado") from exc
    index["Evidencia"] = header.index("Evidencia") if "Evidencia" in header else -1

    rows: list[TaskRow] = []
    for number, line in table[1:]:
        cells = split_row(line)
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue
        if len(cells) <= max(index.values()):
            raise StateError(f"{path}:{number}: fila con menos columnas que el encabezado")
        task_id = cells[index["ID"]]
        if not re.fullmatch(r"T-[A-Z]+-\d+", task_id):
            continue
        evidence = cells[index["Evidencia"]] if index["Evidencia"] >= 0 else ""
        rows.append(
            TaskRow(
                task_id=task_id,
                status=parse_status(cells[index["Estado"]]),
                evidence=evidence,
                acs=tuple(dict.fromkeys(AC_RE.findall(cells[index["AC"]]))),
                line=number,
            )
        )
    if not rows:
        raise StateError(f"{path}: no se encontró ninguna fila T-XX-NN")
    return rows


def git_commits(root: Path) -> dict[str, Commit]:
    completed = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "-C", str(root), "log", "--format=%H%x1f%s%x1e"],  # noqa: S607 - git from PATH
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise StateError(f"git log falló en {root}: {completed.stderr.strip()}")
    commits: dict[str, Commit] = {}
    for record in completed.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, _, subject = record.partition("\x1f")
        pr_match = PR_RE.search(subject)
        pr = pr_match.group(1) if pr_match else ""
        for task_id in TASK_RE.findall(subject):
            current = commits.get(task_id)
            if current is None or (not current.pr and pr):
                commits[task_id] = Commit(sha=sha, pr=pr, subject=subject)
    return commits


def test_corpus(root: Path) -> list[tuple[str, str]]:
    paths: set[Path] = set()
    for pattern in TEST_PATTERNS:
        paths.update(root.glob(pattern))
    corpus: list[tuple[str, str]] = []
    for path in sorted(paths):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        corpus.append((path.relative_to(root).as_posix(), text))
    return corpus


def tests_for(ac: str, corpus: list[tuple[str, str]]) -> list[str]:
    variants = (ac, ac.replace("-", "_"))
    return [name for name, text in corpus if any(variant in text for variant in variants)]


def verification_acs(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = split_row(line)
        if cells and AC_RE.fullmatch(cells[0]):
            found.add(cells[0])
    return found


def spec_state(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    block = text.split("---", 2)[1]
    match = re.search(r"^estado:\s*(\S+)", block, re.MULTILINE)
    return match.group(1) if match else ""


def check_spec(
    module_dir: Path,
    commits: dict[str, Commit],
    corpus: list[tuple[str, str]],
    baseline: dict[str, object],
) -> SpecResult:
    module = module_dir.name
    tasks = read_tasks(module_dir / "tasks.md")
    spec_path = module_dir / "spec.sdd.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    acs = set(AC_RE.findall(spec_text))
    ver_path = module_dir / "verification.md"
    ver_acs = verification_acs(ver_path)
    state = spec_state(spec_path)
    allowed = allowed_missing(baseline, module)
    drift: list[str] = []

    for task in tasks:
        commit = commits.get(task.task_id)
        if task.status == "?":
            drift.append(f"{task.task_id}: estado inválido en la fila {task.line}")
        elif task.status in MERGED:
            if commit is None:
                drift.append(
                    f"{task.task_id}: marcada {task.status} pero no hay commit que la nombre"
                )
                continue
            pr = PR_RE.search(task.evidence)
            sha = SHA_RE.search(task.evidence)
            if not pr or not sha:
                drift.append(f"{task.task_id}: {task.status} sin PR y SHA en Evidencia")
            else:
                if commit.pr and pr.group(1) != commit.pr:
                    drift.append(
                        f"{task.task_id}: la Evidencia cita PR #{pr.group(1)} "
                        f"pero git dice #{commit.pr}"
                    )
                if not commit.sha.startswith(sha.group(0)):
                    drift.append(
                        f"{task.task_id}: la Evidencia cita SHA {sha.group(0)} "
                        f"pero git dice {commit.sha[:7]}"
                    )
        elif task.status in PENDING:
            if commit is not None:
                drift.append(
                    f"{task.task_id}: mergeada en git (PR #{commit.pr or '?'}, "
                    f"{commit.sha[:7]}) pero marcada {task.status}"
                )
        elif task.status == BLOCKED and not Q_RE.search(task.evidence):
            drift.append(f"{task.task_id}: ⛔ sin Q-xxx en Evidencia")

        if task.status == "🧪":
            if not ver_path.is_file():
                drift.append(f"{task.task_id}: 🧪 sin verification.md")
            elif not ver_acs.intersection(task.acs):
                drift.append(f"{task.task_id}: 🧪 sin fila de sus AC en verification.md")

    missing = sorted(ac for ac in acs if not tests_for(ac, corpus))
    for ac in missing:
        if ac not in allowed:
            drift.append(f"{ac}: sin test que lo nombre (ni {ac} ni {ac.replace('-', '_')})")

    if state in FINAL_STATES and not ver_path.is_file():
        drift.append(f"spec {state} sin verification.md")
    if ver_path.is_file():
        for unknown in sorted(ver_acs - acs):
            drift.append(f"verification.md menciona {unknown}, que no existe en la spec")

    return SpecResult(
        module=module,
        tasks=tasks,
        acs=acs,
        missing=missing,
        allowed_missing=allowed,
        drift=drift,
    )


def conciliation_table(tasks: list[TaskRow], commits: dict[str, Commit]) -> list[str]:
    lines = ["| Tarea | PR | SHA | Estado |", "|---|---|---|---|"]
    for task in tasks:
        commit = commits.get(task.task_id)
        pr = f"#{commit.pr}" if commit and commit.pr else "—"
        sha = commit.sha[:7] if commit else "—"
        lines.append(f"| {task.task_id} | {pr} | {sha} | {task.status} |")
    return lines


def write_conciliation(module_dir: Path, tasks: list[TaskRow], commits: dict[str, Commit]) -> None:
    path = module_dir / "tasks.md"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        raise StateError(f"{path}: faltan los marcadores {BEGIN} / {END}")
    block = "\n".join(conciliation_table(tasks, commits))
    replacement = f"{BEGIN}\n{block}\n{END}"
    path.write_text(pattern.sub(replacement, text, count=1), encoding="utf-8", newline="\n")


def summarize(result: SpecResult) -> str:
    counts = dict.fromkeys(STATUS_ORDER, 0)
    for task in result.tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    task_part = ", ".join(f"{counts[symbol]} {symbol}" for symbol in STATUS_ORDER if counts[symbol])
    covered = len(result.acs) - len(result.missing)
    allowed = len(set(result.missing) & result.allowed_missing)
    return (
        f"{result.module}: {len(result.tasks)} tareas ({task_part}); "
        f"{len(result.acs)} AC ({covered} con test que nombra el AC, "
        f"{len(result.missing)} sin test con su ID, {allowed} en baseline)"
    )
