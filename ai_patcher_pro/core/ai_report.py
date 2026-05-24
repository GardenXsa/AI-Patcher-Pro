"""
AI-friendly report builder for AI Patcher Pro.

Screenshots are inconvenient for LLMs. This module produces a plain-text,
copyable, structured report that can be sent directly to GPT.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


MAX_BLOCK_CHARS = 12_000
MAX_DIFF_LINES = 120


def _safe(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _clip(text: str, limit: int = MAX_BLOCK_CHARS) -> str:
    text = _safe(text)
    if len(text) <= limit:
        return text
    hidden = len(text) - limit
    return text[:limit].rstrip() + f"\n... [truncated: {hidden} chars hidden]"


def _fence(language: str, content: str) -> str:
    body = _clip(content).rstrip()
    if not body:
        body = "(empty)"
    return f"~~~{language}\n{body}\n~~~"


def _op_path(op: Dict[str, Any]) -> str:
    return _safe(op.get("path") or op.get("file") or "?")


def _op_action(op: Dict[str, Any]) -> str:
    return _safe(op.get("action") or op.get("op") or "?")


def _count_status(items: Iterable[Dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("status") == status)


def build_ai_patch_report(
    patch_name: str,
    workspace: str,
    processed_operations: List[Dict[str, Any]],
    command_results: List[Dict[str, Any]],
    raw_operations: Optional[List[Dict[str, Any]]] = None,
    current_phase: str = "",
    patch_written: bool = False,
    note: str = "",
) -> str:
    """Builds a complete plain-text report for GPT."""
    raw_operations = raw_operations or []
    project_name = os.path.basename(os.path.normpath(workspace)) or workspace
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    op_success = _count_status(processed_operations, "success")
    op_applied = _count_status(processed_operations, "applied")
    op_already = _count_status(processed_operations, "already_applied")
    op_errors = _count_status(processed_operations, "error")
    cmd_success = _count_status(command_results, "success")
    cmd_errors = _count_status(command_results, "error")

    has_errors = op_errors > 0 or cmd_errors > 0
    if has_errors:
        request = (
            "Нужно исправить ошибки и вернуть новый JSON-патч для AI Patcher Pro. "
            "Не проси скриншоты: все важные данные ниже текстом."
        )
    elif patch_written:
        request = (
            "Патч применён. Проверь результат по отчёту и предложи следующий безопасный шаг, "
            "если он нужен."
        )
    else:
        request = (
            "Патч проанализирован, но ещё не записан на диск. Проверь, выглядит ли применение безопасным."
        )

    parts: List[str] = [
        "# PATCH_RESULT.md / AI Patcher Pro report",
        "",
        "Этот отчёт создан специально для GPT. Он заменяет скриншоты и не требует угадывать состояние UI.",
        "",
        "## Request for GPT",
        request,
        "",
        "## Session",
        f"- Project: {project_name}",
        f"- Workspace: {workspace}",
        f"- Patch: {patch_name or 'Без имени'}",
        f"- Created: {created_at}",
        f"- Current phase: {current_phase or 'unknown'}",
        f"- Patch written to disk: {'yes' if patch_written else 'no'}",
        "",
        "## Summary",
        f"- Raw operations: {len(raw_operations)}",
        f"- Processed operations: {len(processed_operations)}",
        f"- Found but not applied: {op_success}",
        f"- Applied: {op_applied}",
        f"- Already applied / skipped: {op_already}",
        f"- Operation errors: {op_errors}",
        f"- Commands OK: {cmd_success}",
        f"- Command errors: {cmd_errors}",
        "",
    ]

    if note.strip():
        parts.extend(["## Note", note.strip(), ""])

    if not processed_operations and not command_results:
        parts.extend(["## State", "No analyzed operations or command results yet.", ""])

    if processed_operations:
        parts.extend(["## Operations", ""])
        for i, item in enumerate(processed_operations, 1):
            op = item.get("op", {}) or {}
            status = _safe(item.get("status"), "unknown")
            error = _safe(item.get("error"))
            search_method = _safe(item.get("search_method"))
            suggestions = item.get("suggestions") or []
            diff_lines = item.get("diff") or []

            parts.extend([
                f"### Operation {i}: {_op_action(op)} → {_op_path(op)}",
                f"- Status: {status}",
            ])
            if search_method:
                parts.append(f"- Search method: {search_method}")
            if error:
                parts.append(f"- Error: {error}")

            search_text = _safe(op.get("search") or op.get("original") or op.get("find"))
            content_text = _safe(op.get("content") or op.get("text") or op.get("code"))

            if search_text and status == "error":
                parts.extend(["", "Search text from patch:", _fence("text", search_text)])

            if content_text and status in ("error", "already_applied"):
                parts.extend(["", "Replacement/content text:", _fence("text", content_text)])

            if diff_lines:
                diff_preview = "\n".join(_safe(line) for line in diff_lines[:MAX_DIFF_LINES])
                if len(diff_lines) > MAX_DIFF_LINES:
                    diff_preview += f"\n... [truncated: {len(diff_lines) - MAX_DIFF_LINES} diff lines hidden]"
                parts.extend(["", "Diff preview:", _fence("diff", diff_preview)])

            if suggestions:
                parts.extend(["", "Fuzzy suggestions:"])
                for s_idx, suggestion in enumerate(suggestions, 1):
                    try:
                        ratio, text = suggestion
                    except (TypeError, ValueError):
                        ratio, text = 0, suggestion
                    percent = int(float(ratio) * 100) if ratio else 0
                    parts.extend([f"Suggestion {s_idx}: {percent}%", _fence("text", _safe(text))])

            parts.append("")

    if command_results:
        parts.extend(["## Commands", ""])
        for i, result in enumerate(command_results, 1):
            cmd = _safe(result.get("cmd"), "?")
            desc = _safe(result.get("description"))
            status = _safe(result.get("status"), "unknown")
            returncode = _safe(result.get("returncode"), "?")
            stdout = _safe(result.get("stdout"))
            stderr = _safe(result.get("stderr"))
            warnings = result.get("warnings") or []

            parts.extend([
                f"### Command {i}",
                f"- Command: `{cmd}`",
                f"- Status: {status}",
                f"- Return code: {returncode}",
            ])
            if desc:
                parts.append(f"- Description: {desc}")
            if warnings:
                parts.append("- Warnings: " + "; ".join(_safe(w) for w in warnings))
            if stdout.strip():
                parts.extend(["", "stdout:", _fence("text", stdout)])
            if stderr.strip():
                parts.extend(["", "stderr:", _fence("text", stderr)])
            parts.append("")

    parts.extend([
        "## Rules for GPT response",
        "- Return a JSON patch for AI Patcher Pro.",
        "- Do not ask for screenshots if the needed text is present here.",
        "- On Windows, prefer `py -m ...` for Python commands.",
        "- If the problem is command-only, return a command-only patch with `run: after_analysis` when no file operations are needed.",
    ])

    return "\n".join(parts).rstrip() + "\n"
