"""
Workflow helpers for AI Patcher Pro.

This module turns AI Patcher Pro from a plain patch applier into a safer
working assistant:
- project profiles;
- git safety diagnostics;
- patch fingerprint registry;
- predefined verification profiles;
- GPT handoff bundle text;
- simple project-rule checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Tuple


STATE_DIR = ".ai_patcher"
PATCH_REGISTRY_FILE = "applied_patches.json"
PROJECT_PROFILE_FILE = "project_profile.json"


DEFAULT_PROFILE: Dict[str, Any] = {
    "name": "Generic project",
    "kind": "generic",
    "rules": [
        "Return JSON patches for AI Patcher Pro.",
        "Prefer small, reviewable changes.",
        "Use project-relevant tests after meaningful changes.",
    ],
    "check_profiles": {
        "quick": [
            "py -m compileall ai_patcher_pro tests"
        ],
        "parser": [
            "py -m pytest tests/test_json_parser.py tests/test_json_parser_robust.py -v"
        ],
        "scanner": [
            "py -m pytest tests/test_scanner.py tests/test_scanner_tab.py -v"
        ],
        "ui": [
            "py -m pytest tests/test_main_window_layout.py tests/test_scanner_tab.py -v"
        ],
        "full": [
            "py -m pytest -v"
        ],
        "build_exe": [
            "py build.py"
        ],
    },
    "required_files_for_runtime_changes": [],
    "forbidden_patterns": [],
}


AI_PATCHER_PROFILE: Dict[str, Any] = {
    "name": "AI Patcher Pro",
    "kind": "ai_patcher_pro",
    "rules": [
        "Return JSON patches for AI Patcher Pro.",
        "Use py -m ... for Python commands on Windows.",
        "Run compileall before building EXE.",
        "Do not build EXE when compileall fails.",
        "Prefer text reports for GPT instead of screenshots.",
    ],
    "check_profiles": {
        "quick": [
            "py -m compileall ai_patcher_pro tests"
        ],
        "parser": [
            "py -m pytest tests/test_json_parser.py tests/test_json_parser_robust.py -v"
        ],
        "scanner": [
            "py -m pytest tests/test_scanner.py tests/test_scanner_tab.py -v"
        ],
        "ui": [
            "py -m pytest tests/test_main_window_layout.py tests/test_scanner_tab.py -v"
        ],
        "full": [
            "py -m pytest tests/test_ai_report.py tests/test_json_parser.py tests/test_json_parser_robust.py tests/test_patcher.py tests/test_scanner.py tests/test_scanner_tab.py tests/test_gpt_context.py -v"
        ],
        "build_exe": [
            "py -m compileall ai_patcher_pro tests",
            "py build.py"
        ],
    },
    "required_files_for_runtime_changes": [],
    "forbidden_patterns": [],
}


METEREA_PROFILE: Dict[str, Any] = {
    "name": "Хроники Метерии",
    "kind": "meterea_chronicles",
    "rules": [
        "Return JSON patches for AI Patcher Pro.",
        "Do not suggest Codex.",
        "Avoid unnecessary Python scripts unless explicitly requested.",
        "Prefer data-driven architecture over hardcoded IDs.",
        "Keep docs/AI_PATCHER_WORKLOG.md updated after meaningful changes.",
        "Keep docs/DATA_DRIVEN_MIGRATION_PLAN.md updated after meaningful migration changes.",
        "After green checks, recommend commit/push checkpoint.",
    ],
    "check_profiles": {
        "quick": [
            "node tools/runtime_smoke_check.js"
        ],
        "runtime": [
            "node tools/runtime_smoke_check.js"
        ],
        "data_contract": [
            "node tools/runtime_smoke_check.js",
            "py tools/validate_data_contract.py"
        ],
        "engine_build": [
            "g++ -std=c++17 -O2 -static -o engine/meterea_engine.exe engine/meterea_engine.cpp engine/item_system.cpp"
        ],
        "git_status": [
            "git status --short",
            "git log --oneline --decorate --graph --all -10"
        ],
    },
    "required_files_for_runtime_changes": [
        "docs/AI_PATCHER_WORKLOG.md",
        "docs/DATA_DRIVEN_MIGRATION_PLAN.md"
    ],
    "forbidden_patterns": [
        "hardcoded",
        "HARDCODED",
        "TODO hardcode"
    ],
}


@dataclass
class GitSafetyStatus:
    is_repo: bool = False
    branch: str = ""
    upstream: str = ""
    detached: bool = False
    rebase_in_progress: bool = False
    merge_in_progress: bool = False
    dirty: bool = False
    staged_count: int = 0
    unstaged_count: int = 0
    untracked_count: int = 0
    ahead: int = 0
    behind: int = 0
    origin_head: str = ""
    warnings: List[str] = field(default_factory=list)
    safe_next_steps: List[str] = field(default_factory=list)
    raw_status: str = ""
    graph: str = ""


def ensure_state_dir(root_path: str) -> str:
    path = os.path.join(root_path, STATE_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _run(root_path: str, args: List[str], timeout: int = 20) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=root_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out: {' '.join(args)}"
    except OSError as e:
        return 1, "", str(e)


def canonical_patch_text(patch_name: str, raw_operations: List[Dict[str, Any]], commands: List[Dict[str, Any]]) -> str:
    payload = {
        "patch_name": patch_name or "",
        "operations": raw_operations or [],
        "commands": commands or [],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def patch_fingerprint(patch_name: str, raw_operations: List[Dict[str, Any]], commands: List[Dict[str, Any]]) -> str:
    text = canonical_patch_text(patch_name, raw_operations, commands)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _registry_path(root_path: str) -> str:
    return os.path.join(ensure_state_dir(root_path), PATCH_REGISTRY_FILE)


def load_patch_registry(root_path: str) -> Dict[str, Any]:
    path = _registry_path(root_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("patches", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "patches": []}


def find_applied_patch(root_path: str, fingerprint: str) -> Dict[str, Any] | None:
    registry = load_patch_registry(root_path)
    for item in registry.get("patches", []):
        if item.get("fingerprint") == fingerprint:
            return item
    return None


def mark_patch_applied(
    root_path: str,
    fingerprint: str,
    patch_name: str,
    files: List[str],
    summary: str = "",
) -> str:
    registry = load_patch_registry(root_path)
    patches = registry.setdefault("patches", [])

    existing = None
    for item in patches:
        if item.get("fingerprint") == fingerprint:
            existing = item
            break

    payload = {
        "fingerprint": fingerprint,
        "patch_name": patch_name or "Без имени",
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "files": sorted(set(files)),
        "summary": summary,
    }

    if existing:
        existing.update(payload)
    else:
        patches.append(payload)

    path = _registry_path(root_path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def detect_project_profile(root_path: str) -> Dict[str, Any]:
    """Detects or loads a project profile."""
    profile_path = os.path.join(ensure_state_dir(root_path), PROJECT_PROFILE_FILE)
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("name"):
            return merge_profile(DEFAULT_PROFILE, data)
    except (OSError, json.JSONDecodeError):
        pass

    names = set(os.listdir(root_path)) if os.path.isdir(root_path) else set()
    if "ai_patcher_pro" in names and "build.py" in names:
        return AI_PATCHER_PROFILE.copy()
    if "GameBuilder.py" in names or "engine" in names and "data" in names and "js" in names:
        return METEREA_PROFILE.copy()
    return DEFAULT_PROFILE.copy()


def merge_profile(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = dict(result[key])
            merged.update(value)
            result[key] = merged
        else:
            result[key] = value
    return result


def save_project_profile(root_path: str, profile: Dict[str, Any] | None = None) -> str:
    profile = profile or detect_project_profile(root_path)
    path = os.path.join(ensure_state_dir(root_path), PROJECT_PROFILE_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def get_check_profiles(root_path: str) -> Dict[str, List[str]]:
    profile = detect_project_profile(root_path)
    checks = profile.get("check_profiles") or {}
    return {str(k): [str(cmd) for cmd in v] for k, v in checks.items() if isinstance(v, list)}


def get_check_commands(root_path: str, profile_name: str) -> List[Dict[str, str]]:
    checks = get_check_profiles(root_path)
    commands = checks.get(profile_name, [])
    return [
        {
            "cmd": cmd,
            "run": "after_apply",
            "description": f"Workflow check: {profile_name}",
        }
        for cmd in commands
    ]


def git_safety_status(root_path: str) -> GitSafetyStatus:
    status = GitSafetyStatus()

    rc, out, err = _run(root_path, ["git", "rev-parse", "--is-inside-work-tree"])
    if rc != 0 or out.strip() != "true":
        status.warnings.append("Это не git-репозиторий или Git недоступен.")
        status.safe_next_steps.append("Выберите корень git-репозитория или работайте без Git Safety.")
        return status

    status.is_repo = True

    rc, out, _ = _run(root_path, ["git", "branch", "--show-current"])
    status.branch = out.strip()
    status.detached = not bool(status.branch)

    rc, out, _ = _run(root_path, ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if rc == 0:
        status.upstream = out.strip()

    git_dir_rc, git_dir, _ = _run(root_path, ["git", "rev-parse", "--git-dir"])
    if git_dir_rc == 0:
        git_dir = git_dir.strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.join(root_path, git_dir)
        status.rebase_in_progress = os.path.exists(os.path.join(git_dir, "rebase-merge")) or os.path.exists(os.path.join(git_dir, "rebase-apply"))
        status.merge_in_progress = os.path.exists(os.path.join(git_dir, "MERGE_HEAD"))

    rc, out, _ = _run(root_path, ["git", "status", "--short"])
    status.raw_status = out.strip()
    if out.strip():
        status.dirty = True
    for line in out.splitlines():
        if not line:
            continue
        xy = line[:2]
        if xy == "??":
            status.untracked_count += 1
        else:
            if xy[0] != " ":
                status.staged_count += 1
            if xy[1] != " ":
                status.unstaged_count += 1

    rc, out, _ = _run(root_path, ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"])
    if rc == 0:
        parts = out.split()
        if len(parts) == 2:
            status.ahead = int(parts[0])
            status.behind = int(parts[1])

    rc, out, _ = _run(root_path, ["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    if rc == 0:
        status.origin_head = out.strip().replace("refs/remotes/origin/", "origin/")

    rc, out, _ = _run(root_path, ["git", "log", "--oneline", "--decorate", "--graph", "--all", "-10"])
    if rc == 0:
        status.graph = out.strip()

    if status.detached:
        status.warnings.append("Detached HEAD: текущий коммит не привязан к ветке.")
        status.safe_next_steps.append("Создать recovery-ветку: git switch -c recovery/<name>")
    if status.rebase_in_progress:
        status.warnings.append("Rebase in progress: сейчас нельзя делать обычный pull/push вслепую.")
        status.safe_next_steps.append("Если всё чисто: git rebase --continue. Перед этим можно создать backup branch.")
    if status.merge_in_progress:
        status.warnings.append("Merge in progress: сначала завершите или отмените merge.")
    if status.ahead and status.behind:
        status.warnings.append(f"Ветка diverged: ahead {status.ahead}, behind {status.behind}.")
        status.safe_next_steps.append("Сначала сохранить backup branch, затем решать rebase/merge/force-with-lease.")
    elif status.ahead:
        status.safe_next_steps.append(f"Можно пушить {status.ahead} локальных commit(s), если проверки зелёные.")
    elif status.behind:
        status.safe_next_steps.append(f"Локальная ветка отстаёт на {status.behind}; сначала pull/rebase после проверки статуса.")
    if status.dirty:
        status.warnings.append("Есть локальные изменения.")
        status.safe_next_steps.append("Перед рискованными действиями сохранить local_diff.txt или сделать commit/stash.")
    if not status.warnings:
        status.safe_next_steps.append("Git-состояние выглядит безопасно. Можно продолжать рабочий цикл.")

    return status


def format_git_safety_report(root_path: str) -> str:
    s = git_safety_status(root_path)
    lines = [
        "# Git Safety Report",
        "",
        f"Workspace: {root_path}",
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Status",
        f"- Is repo: {'yes' if s.is_repo else 'no'}",
        f"- Branch: {s.branch or '(detached/no branch)'}",
        f"- Upstream: {s.upstream or '(none)'}",
        f"- Origin HEAD: {s.origin_head or '(unknown)'}",
        f"- Detached HEAD: {'yes' if s.detached else 'no'}",
        f"- Rebase in progress: {'yes' if s.rebase_in_progress else 'no'}",
        f"- Merge in progress: {'yes' if s.merge_in_progress else 'no'}",
        f"- Dirty: {'yes' if s.dirty else 'no'}",
        f"- Staged: {s.staged_count}",
        f"- Unstaged: {s.unstaged_count}",
        f"- Untracked: {s.untracked_count}",
        f"- Ahead: {s.ahead}",
        f"- Behind: {s.behind}",
        "",
        "## Warnings",
    ]
    lines.extend([f"- {w}" for w in s.warnings] or ["- None"])
    lines.extend(["", "## Safe next steps"])
    lines.extend([f"- {step}" for step in s.safe_next_steps] or ["- None"])

    if s.raw_status:
        lines.extend(["", "## git status --short", "~~~text", s.raw_status, "~~~"])
    if s.graph:
        lines.extend(["", "## git graph", "~~~text", s.graph, "~~~"])

    return "\n".join(lines).rstrip() + "\n"


def project_rule_warnings(root_path: str, raw_operations: List[Dict[str, Any]]) -> List[str]:
    profile = detect_project_profile(root_path)
    warnings: List[str] = []
    required_files = set(profile.get("required_files_for_runtime_changes") or [])
    forbidden_patterns = [str(p) for p in profile.get("forbidden_patterns") or []]

    changed_files = set()
    touched_runtime = False
    for item in raw_operations:
        op = item.get("op", item) if isinstance(item, dict) else {}
        if not isinstance(op, dict):
            continue
        path = op.get("path") or op.get("file") or ""
        if path:
            changed_files.add(path)
        if path.startswith(("engine/", "js/", "data/", "mods/", "script.js", "index.html")):
            touched_runtime = True
        content = "\n".join(str(op.get(k, "")) for k in ("search", "content", "text", "code"))
        for pattern in forbidden_patterns:
            if pattern and pattern in content:
                warnings.append(f"Патч содержит подозрительный pattern `{pattern}` в операции для `{path}`.")

    if touched_runtime and required_files:
        missing = sorted(required_files - changed_files)
        if missing:
            warnings.append(
                "Патч меняет runtime/data области, но не обновляет обязательные файлы профиля: "
                + ", ".join(missing)
            )

    return warnings


def workflow_status_report(
    root_path: str,
    patch_name: str,
    raw_operations: List[Dict[str, Any]],
    processed_operations: List[Dict[str, Any]],
    command_results: List[Dict[str, Any]],
    patch_written: bool,
) -> str:
    profile = detect_project_profile(root_path)
    git_status = git_safety_status(root_path)
    fingerprint = patch_fingerprint(patch_name, raw_operations, command_results)
    already = find_applied_patch(root_path, fingerprint)
    rule_warnings = project_rule_warnings(root_path, raw_operations)

    errors = sum(1 for op in processed_operations if op.get("status") == "error")
    ready = bool(processed_operations) and errors == 0 and not patch_written
    cmd_errors = sum(1 for cmd in command_results if cmd.get("status") == "error")

    if already:
        next_step = "Патч уже есть в реестре. Не применяй повторно без причины."
    elif errors:
        next_step = "Скопировать отчёт для GPT и попросить исправляющий JSON-патч."
    elif cmd_errors:
        next_step = "Скопировать отчёт команд для GPT и исправить команды/код."
    elif ready:
        next_step = "Патч готов к применению. Проверь Git Safety и применяй один раз."
    elif patch_written:
        next_step = "Запусти подходящую проверку, затем сделай git checkpoint."
    elif git_status.warnings:
        next_step = "Сначала разберись с Git Safety предупреждениями."
    else:
        next_step = "Вставь JSON-патч или подготовь GPT context pack."

    lines = [
        "# Workflow Assistant",
        "",
        f"Project: {profile.get('name', 'Unknown')}",
        f"Workspace: {root_path}",
        f"Patch: {patch_name or 'Без имени'}",
        f"Patch fingerprint: {fingerprint[:16]}...",
        f"Patch written: {'yes' if patch_written else 'no'}",
        "",
        "## Main recommendation",
        next_step,
        "",
        "## Project rules",
    ]
    lines.extend([f"- {rule}" for rule in profile.get("rules", [])])
    lines.extend(["", "## Project rule warnings"])
    lines.extend([f"- {w}" for w in rule_warnings] or ["- None"])
    lines.extend(["", "## Git warnings"])
    lines.extend([f"- {w}" for w in git_status.warnings] or ["- None"])
    lines.extend(["", "## Safe next steps"])
    lines.extend([f"- {s}" for s in git_status.safe_next_steps] or ["- None"])
    lines.extend(["", "## Check profiles"])
    for name, commands in get_check_profiles(root_path).items():
        lines.append(f"### {name}")
        for cmd in commands:
            lines.append(f"- `{cmd}`")
    if already:
        lines.extend([
            "",
            "## Patch registry match",
            f"- Name: {already.get('patch_name', '')}",
            f"- Applied at: {already.get('applied_at', '')}",
            f"- Files: {', '.join(already.get('files', []))}",
        ])
    return "\n".join(lines).rstrip() + "\n"


def gpt_handoff_text(root_path: str, task: str = "") -> str:
    profile = detect_project_profile(root_path)
    git_report = format_git_safety_report(root_path)
    lines = [
        "# GPT handoff",
        "",
        "Продолжи работу по проекту. Ответ нужен JSON-патчем для AI Patcher Pro.",
        "",
        "## Task",
        task.strip() or "Опиши задачу здесь.",
        "",
        "## Source of truth",
        "- GitHub / текущий репозиторий — основной источник кода.",
        "- local_diff.txt — локальные изменения, которых может не быть в GitHub.",
        "- PATCH_RESULT.md — результат применения патча и ошибки.",
        "",
        "## Project profile",
        f"Name: {profile.get('name', 'Unknown')}",
        "",
        "## Rules",
    ]
    lines.extend([f"- {rule}" for rule in profile.get("rules", [])])
    lines.extend(["", git_report])
    return "\n".join(lines).rstrip() + "\n"
