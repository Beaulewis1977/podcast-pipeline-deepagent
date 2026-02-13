#!/usr/bin/env python3
"""Map positional-vs-key=value argument usage for GSD files in ~/.codex.

This script audits GSD prompts/commands/agents/skills and generates a
checklist-style Markdown report with exact file:line targets and suggested
key=value command forms.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TARGET_GLOBS = (
    "prompts/gsd-*.md",
    "prompts/gsd/*.md",
    "commands/gsd/*.md",
    "agents/gsd-*.md",
    "skills/gsd-*/SKILL.md",
)

# Only match actual command invocations, not file paths like agents/gsd-planner.md.
COMMAND_RE = re.compile(r"/(?:gsd:[a-z0-9-]+|prompts:gsd-[a-z0-9-]+)")
ARG_HINT_RE = re.compile(r"^\s*argument-hint:\s*(.+?)\s*$", re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
BARE_COMMAND_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?P<cmd>/(?:prompts:)?gsd(?::|-)[a-z0-9-]+)(?P<tail>.*)$"
)

# Recommended canonical forms for key=value migration.
CANONICAL_FORMS: dict[str, str] = {
    "add-phase": 'description="<text>"',
    "add-todo": 'description="<text>"',
    "audit-milestone": 'version="<milestone-version>"',
    "check-todos": "area=<filter>",
    "complete-milestone": "version=<milestone-version>",
    "debug": 'issue="<description>"',
    "discuss-phase": "phase=<number>",
    "execute-phase": "phase=<number> [--gaps-only]",
    "insert-phase": 'after=<phase-number> description="<text>"',
    "list-phase-assumptions": "phase=<number>",
    "map-codebase": "focus=<tech|arch|quality|concerns>",
    "new-milestone": 'name="<milestone name>"',
    "plan-phase": "phase=<number> [--research] [--skip-research] [--gaps] [--skip-verify]",
    "remove-phase": "phase=<number>",
    "research-phase": "phase=<number>",
    "verify-work": "phase=<number>",
}


@dataclass(frozen=True)
class Finding:
    rel_path: str
    line_no: int
    category: str
    command: str
    line_text: str
    suggestion: str


def iter_target_files(codex_root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in TARGET_GLOBS:
        files.extend(codex_root.glob(pattern))
    gsd_dir = codex_root / "gsd"
    if gsd_dir.exists():
        files.extend(gsd_dir.rglob("*.md"))
    return sorted({p for p in files if p.is_file()})


def clean_token(token: str) -> str:
    return token.strip().strip("`.,;:()[]")


def split_tokens(rest: str) -> list[str]:
    if not rest.strip():
        return []
    text = rest.replace("`", " ")
    raw = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', text)
    tokens = [clean_token(tok) for tok in raw]
    return [tok for tok in tokens if tok]


def normalize_command_name(command: str) -> str:
    # /prompts:gsd-plan-phase -> plan-phase
    # /gsd:plan-phase         -> plan-phase
    value = command.lstrip("/")
    if value.startswith("prompts:gsd-"):
        return value[len("prompts:gsd-") :]
    if value.startswith("gsd:"):
        return value[len("gsd:") :]
    return value


def command_name_from_rel_path(rel_path: str) -> str | None:
    # commands/gsd/plan-phase.md       -> plan-phase
    # prompts/gsd-plan-phase.md        -> plan-phase
    # prompts/gsd/plan-phase.md        -> plan-phase
    if rel_path.startswith("commands/gsd/") and rel_path.endswith(".md"):
        return rel_path[len("commands/gsd/") : -3]
    if rel_path.startswith("prompts/gsd-") and rel_path.endswith(".md"):
        return rel_path[len("prompts/gsd-") : -3]
    if rel_path.startswith("prompts/gsd/") and rel_path.endswith(".md"):
        return rel_path[len("prompts/gsd/") : -3]
    return None


def build_suggestion(command: str) -> str:
    name = normalize_command_name(command)
    form = CANONICAL_FORMS.get(name)
    if form:
        return f"{command} {form}"
    return f"{command} <name>=<value>"


def is_positional_arg_usage(tokens: list[str]) -> bool:
    if not tokens:
        return False
    non_flags = [tok for tok in tokens if not tok.startswith("--")]
    if not non_flags:
        return False
    return not any("=" in tok for tok in non_flags)


def is_usage_context(line: str) -> bool:
    lower = line.lower()
    if "usage:" in lower or "example:" in lower:
        return True
    if "run /" in lower or "execute:" in lower or "next:" in lower:
        return True
    if line.strip().startswith("/"):
        return True
    return bool(line.strip().startswith("`/"))


def truncate_arg_tokens(tokens: list[str]) -> list[str]:
    stopwords = {
        "and",
        "or",
        "to",
        "with",
        "before",
        "after",
        "instead",
        "for",
        "if",
        "then",
        "which",
        "that",
        "when",
        "while",
        "so",
        "because",
    }
    out: list[str] = []
    for tok in tokens:
        low = tok.lower()
        if tok.startswith("/"):
            break
        if low in stopwords:
            break
        if tok.startswith("#") or tok.startswith("("):
            break
        if tok in {"|", "—", "→", "->"}:
            break
        out.append(tok)
    return out


def collect_command_findings_from_text(
    rel_path: str, line_no: int, line_text: str, text: str
) -> list[Finding]:
    findings: list[Finding] = []
    for cmd_match in COMMAND_RE.finditer(text):
        command = cmd_match.group(0)
        cmd_name = normalize_command_name(command)
        # Only flag commands we know how to migrate.
        if cmd_name not in CANONICAL_FORMS:
            continue
        tail = text[cmd_match.end() :]
        tokens = truncate_arg_tokens(split_tokens(tail))
        if is_positional_arg_usage(tokens):
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=line_no,
                    category="command-positional-args",
                    command=command,
                    line_text=line_text.strip(),
                    suggestion=build_suggestion(command),
                )
            )
    return findings


def collect_findings(codex_root: Path, files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int, str, str, str]] = set()
    for path in files:
        rel_path = str(path.relative_to(codex_root))
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(content.splitlines(), start=1):
            # Frontmatter hint checks
            hint_match = ARG_HINT_RE.match(line)
            if hint_match:
                hint = hint_match.group(1).strip()
                if "=" not in hint:
                    cmd_name = command_name_from_rel_path(rel_path)
                    hint_form = (
                        CANONICAL_FORMS.get(cmd_name, "<name>=<value>")
                        if cmd_name
                        else "<name>=<value>"
                    )
                    findings.append(
                        Finding(
                            rel_path=rel_path,
                            line_no=line_no,
                            category="argument-hint-positional",
                            command="argument-hint",
                            line_text=line.strip(),
                            suggestion=f"argument-hint: {hint_form}",
                        )
                    )

            # Command checks in inline code spans (most reliable examples).
            for span_match in CODE_SPAN_RE.finditer(line):
                span_text = span_match.group(1)
                findings.extend(
                    collect_command_findings_from_text(rel_path, line_no, line, span_text)
                )

            # Command checks in bare command lines.
            bare = BARE_COMMAND_LINE_RE.match(line)
            if bare:
                text = f"{bare.group('cmd')}{bare.group('tail')}"
                findings.extend(collect_command_findings_from_text(rel_path, line_no, line, text))
                continue

            # Plain-text usage lines that are not in code spans.
            if is_usage_context(line):
                findings.extend(collect_command_findings_from_text(rel_path, line_no, line, line))
    deduped: list[Finding] = []
    for finding in findings:
        key = (
            finding.rel_path,
            finding.line_no,
            finding.category,
            finding.command,
            finding.suggestion,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def render_report(
    codex_root: Path, files: list[Path], findings: list[Finding], out_path: Path
) -> str:
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    files_with_issues = sorted({f.rel_path for f in findings})
    by_category: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for f in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1
        by_file[f.rel_path] = by_file.get(f.rel_path, 0) + 1

    lines: list[str] = []
    lines.append("# GSD Key=Value Migration Checklist")
    lines.append("")
    lines.append(f"- Audit time: `{now}`")
    lines.append(f"- Codex root scanned: `{codex_root}`")
    lines.append(f"- GSD files scanned: **{len(files)}**")
    lines.append(f"- Files with issues: **{len(files_with_issues)}**")
    lines.append(f"- Total checklist items: **{len(findings)}**")
    lines.append("")
    lines.append("## Issue Summary")
    lines.append("")
    if by_category:
        for category, count in sorted(by_category.items()):
            lines.append(f"- `{category}`: **{count}**")
    else:
        lines.append("- No positional usage detected.")
    lines.append("")
    lines.append("## Canonical Command Forms")
    lines.append("")
    lines.append("| Command | Key=Value Form |")
    lines.append("|---|---|")
    for command, form in sorted(CANONICAL_FORMS.items()):
        lines.append(f"| `/gsd:{command}` | `{form}` |")
    lines.append("")
    lines.append("## Global Checklist")
    lines.append("")
    lines.append("- [ ] Update all `argument-hint:` entries that are still positional.")
    lines.append("- [ ] Update all command examples that pass bare values (e.g. `... 4`).")
    lines.append('- [ ] Update all routing/"next command" snippets to key=value form.')
    lines.append("- [ ] Re-run this mapper and confirm `Total checklist items: 0`.")
    lines.append("")
    lines.append("## Hotspots (Fix First)")
    lines.append("")
    lines.append("| File | Items |")
    lines.append("|---|---:|")
    for rel_path, count in sorted(by_file.items(), key=lambda x: (-x[1], x[0]))[:20]:
        lines.append(f"| `{rel_path}` | {count} |")
    lines.append("")
    lines.append("## File Checklist")
    lines.append("")

    if not findings:
        lines.append("- [x] No file-level changes required.")
    else:
        grouped: dict[str, list[Finding]] = {}
        for finding in findings:
            grouped.setdefault(finding.rel_path, []).append(finding)

        for rel_path in sorted(grouped):
            file_findings = sorted(grouped[rel_path], key=lambda x: x.line_no)
            lines.append(f"### `{rel_path}`")
            lines.append("")
            for finding in file_findings:
                lines.append(f"- [ ] `{rel_path}:{finding.line_no}` `{finding.category}`")
                lines.append(f"  Current: `{finding.line_text}`")
                lines.append(f"  Suggest: `{finding.suggestion}`")
            lines.append("")

    report = "\n".join(lines).rstrip() + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a GSD command-argument migration checklist for ~/.codex."
    )
    parser.add_argument(
        "--codex-root",
        default=str(Path.home() / ".codex"),
        help="Path to codex config root (default: ~/.codex)",
    )
    parser.add_argument(
        "--out",
        default=str(
            Path.cwd()
            / "docs"
            / "reports"
            / f"{dt.datetime.now(dt.UTC).date().isoformat()}-gsd-keyvalue-migration-checklist.md"
        ),
        help="Output markdown report path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    codex_root = Path(args.codex_root).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    files = iter_target_files(codex_root)
    findings = collect_findings(codex_root, files)
    render_report(codex_root, files, findings, out_path)
    sys.stdout.write(f"Wrote checklist report: {out_path}\n")
    sys.stdout.write(f"GSD files scanned: {len(files)}\n")
    sys.stdout.write(f"Checklist items: {len(findings)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
