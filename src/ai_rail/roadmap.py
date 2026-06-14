from __future__ import annotations

import re
from typing import Any

REMOTE_MEMORY_START = "<!-- AI RAIL PROJECT MEMORY START -->"
REMOTE_MEMORY_END = "<!-- AI RAIL PROJECT MEMORY END -->"
LOCAL_ROADMAP_START = "<!-- AI RAIL MANAGED ROADMAP START -->"
LOCAL_ROADMAP_END = "<!-- AI RAIL MANAGED ROADMAP END -->"
RAIL_ROADMAP_START = "<!-- AI RAIL ROADMAP START -->"
RAIL_ROADMAP_END = "<!-- AI RAIL ROADMAP END -->"
RAIL_TASK_ID_PATTERN = r"P\d+-T\d+"
RAIL_TASK_RE = re.compile(r"^- \[(?P<status>[ x])\] (?P<issue>#\d+|TBD) \| (?P<task_id>P\d+-T\d+) \| (?P<title>.+)$")
RAIL_TASK_ID_FIRST_RE = re.compile(rf"^- \[(?P<status>[ x])\] (?P<task_id>{RAIL_TASK_ID_PATTERN}) \| (?P<issue>#\d+|TBD) \| (?P<title>.+)$")
RAIL_PHASE_RE = re.compile(r"^## Phase (?P<phase>P\d+)\b")
RAIL_PHASE_STATUSES = {"planned", "active", "complete", "blocked"}


def roadmap_issue_from_open_issues(open_issues: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, bool]:
    roadmap = [item for item in open_issues if "roadmap:" in str(item.get("title", "")).lower()]
    if not roadmap:
        return None, False
    roadmap = sorted(roadmap, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return roadmap[0], len(roadmap) > 1


def extract_remote_memory(body: str) -> str | None:
    if REMOTE_MEMORY_START not in body or REMOTE_MEMORY_END not in body:
        return None
    return body.split(REMOTE_MEMORY_START, 1)[1].split(REMOTE_MEMORY_END, 1)[0].strip()


def render_managed_roadmap_from_issue(roadmap: dict[str, Any], open_issues: list[dict[str, Any]], closed_issues: list[dict[str, Any]]) -> str:
    body = str(roadmap.get("body") or "").strip() or "_No roadmap body captured._"
    open_impl = [item for item in open_issues if item.get("number") != roadmap.get("number")]
    open_lines = "\n".join(f"- [ ] #{item.get('number')} {item.get('title')}" for item in open_impl) or "- None"
    closed_lines = "\n".join(f"- [x] #{item.get('number')} {item.get('title')}" for item in closed_issues) or "- None"
    next_issue = open_impl[0] if open_impl else None
    next_line = f"#{next_issue.get('number')} {next_issue.get('title')}" if next_issue else "None"
    return f"""## Roadmap

Imported from GitHub roadmap issue #{roadmap.get('number')}: {roadmap.get('title')}

## Roadmap issue body

{body}

## Active execution queue

{open_lines}

## Completed work

{closed_lines}

## Next recommended issue

{next_line}
"""


def default_strict_roadmap_block() -> str:
    return f"""{RAIL_ROADMAP_START}

## Phase P1 - Foundation
Status: active

### Goal
Roadmap needs a Rail-readable phase goal.

### Completion criteria
- Replace this fallback block via rail phase --copy and rail import.

### Tasks
- [ ] P1-T01 | TBD | Replace fallback roadmap with Rail-readable tasks

{RAIL_ROADMAP_END}"""


def extract_strict_roadmap_blocks(text: str) -> list[str]:
    pattern = re.escape(RAIL_ROADMAP_START) + r".*?" + re.escape(RAIL_ROADMAP_END)
    return re.findall(pattern, text, flags=re.DOTALL)


def strict_roadmap_inner(text: str) -> str | None:
    blocks = extract_strict_roadmap_blocks(text)
    if len(blocks) != 1:
        return None
    block = blocks[0]
    return block.split(RAIL_ROADMAP_START, 1)[1].split(RAIL_ROADMAP_END, 1)[0]


def parse_roadmap_task_line(line: str) -> dict[str, str] | None:
    stripped = line.strip()
    match = RAIL_TASK_ID_FIRST_RE.match(stripped)
    if not match:
        match = RAIL_TASK_RE.match(stripped)
    if not match:
        return None
    return {
        "status": match.group("status"),
        "issue": match.group("issue"),
        "task_id": match.group("task_id"),
        "title": match.group("title"),
    }


def active_phase_summary_from_text(text: str) -> dict[str, Any] | None:
    inner = strict_roadmap_inner(text)
    if inner is None:
        return None
    phases: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in inner.splitlines():
        phase_match = RAIL_PHASE_RE.match(line.strip())
        if phase_match:
            current = {"phase": phase_match.group("phase"), "heading": line.strip().removeprefix("## Phase "), "status": None, "tasks": []}
            phases.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("Status:"):
            current["status"] = stripped.split(":", 1)[1].strip()
            continue
        task = parse_roadmap_task_line(line)
        if task:
            current["tasks"].append(task)
    active_phase = next((phase for phase in phases if phase.get("status") == "active"), None)
    if not active_phase:
        return None
    tasks = active_phase["tasks"]
    completed = sum(1 for task in tasks if task["status"] == "x")
    next_task = next((task for task in tasks if task["status"] == " "), None)
    return {
        "phase": active_phase["phase"],
        "heading": active_phase["heading"],
        "completed": completed,
        "total": len(tasks),
        "next_task": next_task,
    }


def ensure_strict_roadmap(managed: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    blocks = extract_strict_roadmap_blocks(managed)
    if len(blocks) == 1:
        return managed.strip(), warnings
    if len(blocks) > 1:
        first = blocks[0]
        managed = re.sub(
            re.escape(RAIL_ROADMAP_START) + r".*?" + re.escape(RAIL_ROADMAP_END),
            lambda match: first if match.start() == managed.find(first) else "",
            managed,
            flags=re.DOTALL,
        )
        warnings.append("Imported roadmap had duplicate strict roadmap blocks; kept the first one.")
        return managed.strip(), warnings
    warnings.append("Imported roadmap is not Rail-readable. Run rail phase --copy, then rail import.")
    return (managed.rstrip() + "\n\n" + default_strict_roadmap_block()).strip(), warnings


def validate_rail_roadmap(text: str) -> list[str]:
    warnings: list[str] = []
    blocks = extract_strict_roadmap_blocks(text)
    if not blocks:
        return ["PROJECT.md roadmap is not Rail-readable. Run rail phase --copy, then rail import."]
    if len(blocks) > 1:
        warnings.append("PROJECT.md has duplicate AI RAIL ROADMAP blocks.")
    inner = blocks[0].split(RAIL_ROADMAP_START, 1)[1].split(RAIL_ROADMAP_END, 1)[0]
    task_ids: set[str] = set()
    issues: set[str] = set()
    saw_phase = False
    current_phase: str | None = None
    active_phases: list[str] = []
    for line in inner.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        phase_match = RAIL_PHASE_RE.match(stripped)
        if phase_match:
            saw_phase = True
            current_phase = phase_match.group("phase")
            continue
        if stripped.startswith("Status:"):
            status = stripped.split(":", 1)[1].strip()
            if status not in RAIL_PHASE_STATUSES:
                warnings.append(f"PROJECT.md roadmap has invalid phase status `{status}`.")
            elif status == "active" and current_phase:
                active_phases.append(current_phase)
            continue
        if stripped.startswith("- ["):
            task = parse_roadmap_task_line(stripped)
            if not task:
                warnings.append(f"PROJECT.md roadmap has malformed task line: {stripped}")
                continue
            task_id = task["task_id"]
            issue = task["issue"]
            if task_id in task_ids:
                warnings.append(f"PROJECT.md roadmap has duplicate task ID `{task_id}`.")
            task_ids.add(task_id)
            if issue != "TBD":
                if issue in issues:
                    warnings.append(f"PROJECT.md roadmap has duplicate issue ref `{issue}`.")
                issues.add(issue)
    if not saw_phase:
        warnings.append("PROJECT.md roadmap has no `## Phase Pn` sections.")
    if len(active_phases) > 1:
        warnings.append("PROJECT.md roadmap has multiple active phases: " + ", ".join(active_phases) + ".")
    return warnings


def project_memory_template(managed: str) -> str:
    return f"""# Project Memory

This file is the local AI Rail project memory and roadmap brain.

GitHub Issues are the active task execution queue.
The GitHub roadmap issue is the remote roadmap mirror.
AI/planning agents create and update the roadmap.
AI Rail imports roadmap memory and tracks completed issue state.

{LOCAL_ROADMAP_START}

{managed.strip()}

{LOCAL_ROADMAP_END}

## Roadmap maintenance rules

- Keep the full roadmap here.
- Keep only the active execution slice as GitHub implementation issues.
- Do not create `.rail/ROADMAP.md`.
- Do not use GitHub Issues for the entire 100-task roadmap.
- Use `rail import` after `rail plan --copy` or `rail phase --copy`.
- Use `rail s` to ship/close one issue and mark it completed locally.
"""


def is_placeholder_project_memory(text: str) -> bool:
    if "CHANGE_ME" not in text:
        return False
    required = ["Product notes", "Stack", "Non-negotiables", "Roadmap maintenance rules"]
    if not all(item in text for item in required):
        return False
    stripped = re.sub(r"<!-- AI RAIL MANAGED ROADMAP START -->.*?<!-- AI RAIL MANAGED ROADMAP END -->", "", text, flags=re.DOTALL)
    defaults = [
        "# Project Memory",
        "This file is the local AI Rail project memory and roadmap brain.",
        "GitHub Issues are the active task execution queue.",
        "The GitHub roadmap issue is the remote roadmap mirror.",
        "AI/planning agents create and update the roadmap.",
        "AI Rail imports roadmap memory and tracks completed issue state.",
        "## Product notes",
        "CHANGE_ME: What does this project do?",
        "## Stack",
        "CHANGE_ME: Main technologies, framework, runtime, database, deployment target.",
        "## Non-negotiables",
        "CHANGE_ME: Constraints, architecture rules, safety rules, and things AI must not break.",
        "## Roadmap maintenance rules",
        "- Keep the full roadmap here.",
        "- Keep only the active execution slice as GitHub implementation issues.",
        "- Do not create `.rail/ROADMAP.md`.",
        "- Do not use GitHub Issues for the entire 100-task roadmap.",
        "- Use `rail import` after `rail plan --copy` or `rail phase --copy`.",
        "- Use `rail s` to ship/close one issue and mark it completed locally.",
    ]
    remainder = stripped
    for item in defaults:
        remainder = remainder.replace(item, "")
    return not remainder.strip()


def roadmap_task_id_mentions(title: str | None, body: str | None) -> set[str]:
    text = f"{title or ''}\n{body or ''}"
    return set(re.findall(RAIL_TASK_ID_PATTERN, text))
