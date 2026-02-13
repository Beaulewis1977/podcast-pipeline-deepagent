#!/usr/bin/env python3
"""Apply key=value argument updates to GSD markdown files under a ~/.codex root.

Focus:
- Update `argument-hint:` frontmatter lines from positional to key=value.
- Update Usage/Example snippets and backticked commands from positional args to key=value.

Safety:
- Only touches files matching known GSD globs under the provided codex root.
- Creates a timestamped backup under /tmp by default.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
import tempfile
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


CANONICAL_HINTS: dict[str, str] = {
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


ARG_HINT_RE = re.compile(r"^(\s*argument-hint:\s*)(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Change:
    rel_path: str
    changed: bool
    notes: list[str]


def iter_target_files(codex_root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in TARGET_GLOBS:
        files.extend(codex_root.glob(pattern))
    gsd_dir = codex_root / "gsd"
    if gsd_dir.exists():
        files.extend(gsd_dir.rglob("*.md"))
    return sorted({p for p in files if p.is_file()})


def command_name_from_path(rel_path: str) -> str | None:
    if rel_path.startswith("commands/gsd/") and rel_path.endswith(".md"):
        return rel_path[len("commands/gsd/") : -3]
    if rel_path.startswith("prompts/gsd-") and rel_path.endswith(".md"):
        return rel_path[len("prompts/gsd-") : -3]
    if rel_path.startswith("prompts/gsd/") and rel_path.endswith(".md"):
        return rel_path[len("prompts/gsd/") : -3]
    return None


def yaml_quote(value: str) -> str:
    # Use single-quoted YAML scalars for safety (handles embedded " easily).
    # Escape any single quotes by doubling, per YAML spec.
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def replace_argument_hint(text: str, rel_path: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    cmd = command_name_from_path(rel_path)
    if not cmd:
        return text, notes

    canonical = CANONICAL_HINTS.get(cmd)
    if not canonical:
        return text, notes

    out_lines: list[str] = []
    changed = False
    for line in text.splitlines():
        m = ARG_HINT_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        prefix, current = m.group(1), m.group(2).strip()
        if "=" in current:
            out_lines.append(line)
            continue
        # Replace positional hint with canonical key=value form.
        out_lines.append(f"{prefix}{yaml_quote(canonical)}")
        changed = True
        notes.append(f"argument-hint -> {canonical}")
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else ""), notes if changed else []


def _cmd_regex(cmd_name: str) -> str:
    # Matches only actual command invocations, not file paths like agents/gsd-planner.md.
    return rf"(?:/gsd:{re.escape(cmd_name)}|/prompts:gsd-{re.escape(cmd_name)})"


def replace_single_arg_commands(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    placeholder_pat = r"[0-9]+(?:\.[0-9]+)?|\{[^}]+\}|\[[^\]]+\]|<[^>]+>|\$\{[^}]+\}"
    single_arg_cmds: list[tuple[str, str, str]] = [
        ("plan-phase", "phase", placeholder_pat),
        ("execute-phase", "phase", placeholder_pat),
        ("verify-work", "phase", placeholder_pat),
        ("discuss-phase", "phase", placeholder_pat),
        ("research-phase", "phase", placeholder_pat),
        ("remove-phase", "phase", placeholder_pat),
        ("list-phase-assumptions", "phase", placeholder_pat),
        ("complete-milestone", "version", placeholder_pat),
        ("audit-milestone", "version", placeholder_pat),
        ("check-todos", "area", r"[A-Za-z0-9_.-]+|\{[^}]+\}|\[[^\]]+\]|<[^>]+>"),
        ("new-milestone", "name", r"\"[^\"]+\"|'[^']+'|\{[^}]+\}|\[[^\]]+\]|<[^>]+>"),
        ("debug", "issue", r"\"[^\"]+\"|'[^']+'|\{[^}]+\}|\[[^\]]+\]|<[^>]+>"),
    ]

    out = text
    for cmd, key, arg_pat in single_arg_cmds:
        pattern = re.compile(
            rf"(?P<cmd>{_cmd_regex(cmd)})\s+(?!{re.escape(key)}=)(?P<arg>{arg_pat})"
        )

        def repl(m: re.Match[str], *, _key: str = key) -> str:
            arg = m.group("arg")
            return f"{m.group('cmd')} {_key}={arg}"

        new_out, n = pattern.subn(repl, out)
        if n:
            notes.append(f"{cmd}: {n} positional -> {key}=")
        out = new_out

    return out, notes


def replace_description_commands(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    out = text

    # Replace backticked add-phase/add-todo examples with unkeyed multiword descriptions.
    for cmd in ("add-phase", "add-todo"):
        cmd_re = _cmd_regex(cmd)
        pattern = re.compile(rf"`(?P<cmd>{cmd_re})\s+(?!description=)(?P<desc>[^`]+?)`")

        def repl(m: re.Match[str]) -> str:
            desc = m.group("desc").strip()
            # Avoid double quoting if already quoted.
            if (desc.startswith('"') and desc.endswith('"')) or (
                desc.startswith("'") and desc.endswith("'")
            ):
                quoted = desc
            else:
                quoted = '"' + desc.replace('"', '\\"') + '"'
            return f"`{m.group('cmd')} description={quoted}`"

        new_out, n = pattern.subn(repl, out)
        if n:
            notes.append(f"{cmd}: {n} examples -> description=")
        out = new_out

    return out, notes


def replace_plain_add_commands(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    out = text

    def quote_desc(desc: str) -> str:
        d = desc.strip()
        if (d.startswith('"') and d.endswith('"')) or (d.startswith("'") and d.endswith("'")):
            return d
        return '"' + d.replace('"', '\\"') + '"'

    for cmd in ("add-phase", "add-todo"):
        cmd_re = _cmd_regex(cmd)
        # Usage: /gsd:add-phase <description>
        out, n1 = re.subn(
            rf"(\bUsage:\s*)(?P<cmd>{cmd_re})\s+<description>",
            r"\\1\\g<cmd> description=\"<text>\"",
            out,
        )
        if n1:
            notes.append(f"{cmd}: {n1} Usage: lines updated")

        # Example: /gsd:add-phase Add authentication system
        pat = re.compile(rf"(\bExample:\s*)(?P<cmd>{cmd_re})\s+(?!description=)(?P<desc>[^\n]+)")

        def repl(m: re.Match[str]) -> str:
            desc = m.group("desc").strip()
            # Trim trailing explanation after arrows or punctuation when present.
            desc = desc.split("→", 1)[0].strip()
            return f"{m.group(1)}{m.group('cmd')} description={quote_desc(desc)}"

        out, n2 = pat.subn(repl, out)
        if n2:
            notes.append(f"{cmd}: {n2} Example: lines updated")

    return out, notes


def replace_help_parentheticals(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    out = text

    # Avoid positional-arg looking tails by using a dash separator.
    patterns = [
        (r"(Usage:\s*`(/gsd:debug)`)\s*\(([^)]+)\)", r"\1 — \3"),
        (r"(Usage:\s*`(/prompts:gsd-debug)`)\s*\(([^)]+)\)", r"\1 — \3"),
        (r"(Usage:\s*`(/gsd:add-todo)`)\s*\(([^)]+)\)", r"\1 — \3"),
        (r"(Usage:\s*`(/prompts:gsd-add-todo)`)\s*\(([^)]+)\)", r"\1 — \3"),
    ]
    for pat, repl in patterns:
        out, n = re.subn(pat, repl, out)
        if n:
            notes.append(f"help: {n} Usage() -> Usage —")
    return out, notes


def replace_plain_todo_and_debug_lines(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    out = text

    # Lines like: /gsd:add-todo Fix modal z-index  # ...
    pat_todo = re.compile(
        rf"(?P<cmd>{_cmd_regex('add-todo')})\s+(?!description=)(?P<desc>[^\n#]+?)(?P<hash>\s+#)"
    )

    def repl_todo(m: re.Match[str]) -> str:
        desc = m.group("desc").strip()
        quoted = '"' + desc.replace('"', '\\"') + '"'
        return f"{m.group('cmd')} description={quoted}{m.group('hash')}"

    out, n1 = pat_todo.subn(repl_todo, out)
    if n1:
        notes.append(f"add-todo: {n1} plain lines -> description=")

    # Lines like: /gsd:debug "..."  # ...
    pat_debug = re.compile(
        rf"(?P<cmd>{_cmd_regex('debug')})\s+(?!issue=)(?P<issue>\"[^\"]+\"|'[^']+')(?P<hash>\s+#)"
    )

    def repl_debug(m: re.Match[str]) -> str:
        return f"{m.group('cmd')} issue={m.group('issue')}{m.group('hash')}"

    out, n2 = pat_debug.subn(repl_debug, out)
    if n2:
        notes.append(f"debug: {n2} plain lines -> issue=")

    return out, notes


def replace_insert_phase(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    out = text
    cmd = "insert-phase"
    cmd_re = _cmd_regex(cmd)

    # Backticked examples: `... 72 Fix critical auth bug`
    pattern = re.compile(
        rf"`(?P<cmd>{cmd_re})\s+(?!after=)(?P<after>[0-9]+(?:\.[0-9]+)?|\{{[^}}]+\}}|\[[^\]]+\]|<[^>]+>)\s+(?P<desc>[^`]+?)`"
    )

    def repl(m: re.Match[str]) -> str:
        after = m.group("after").strip()
        desc = m.group("desc").strip()
        quoted = '"' + desc.replace('"', '\\"') + '"'
        return f"`{m.group('cmd')} after={after} description={quoted}`"

    new_out, n = pattern.subn(repl, out)
    if n:
        notes.append(f"{cmd}: {n} examples -> after= + description=")
    out = new_out

    # Plain "Example: /gsd:insert-phase 72 Fix critical auth bug" lines (non-backticked)
    pattern2 = re.compile(
        rf"(?P<prefix>\bExample:\s*)(?P<cmd>{cmd_re})\s+(?!after=)(?P<after>[0-9]+(?:\.[0-9]+)?)\s+(?P<desc>[^\n]+)"
    )

    def repl2(m: re.Match[str]) -> str:
        after = m.group("after")
        desc = m.group("desc").strip()
        quoted = '"' + desc.replace('"', '\\"') + '"'
        return f"{m.group('prefix')}{m.group('cmd')} after={after} description={quoted}"

    out, n2 = pattern2.subn(repl2, out)
    if n2:
        notes.append(f"{cmd}: {n2} Example: lines updated")

    # Plain occurrences (e.g. in help): /gsd:insert-phase 5 "Critical security fix"
    pattern3 = re.compile(
        rf"(?P<cmd>{cmd_re})\s+(?!after=)(?P<after>[0-9]+(?:\.[0-9]+)?)\s+(?P<desc>\"[^\"]+\"|'[^']+')"
    )

    def repl3(m: re.Match[str]) -> str:
        after = m.group("after")
        desc = m.group("desc")
        return f"{m.group('cmd')} after={after} description={desc}"

    out, n3 = pattern3.subn(repl3, out)
    if n3:
        notes.append(f"{cmd}: {n3} inline occurrences updated")

    # Usage echo lines in insert-phase prompts/commands.
    out, n4 = re.subn(
        r'echo "Usage: /gsd:insert-phase <after> <description>"',
        r'echo "Usage: /gsd:insert-phase after=<phase-number> description=\"<text>\""',
        out,
    )
    if n4:
        notes.append(f"{cmd}: {n4} echo Usage: strings updated")
    out, n5 = re.subn(
        r'echo "Usage: /prompts:gsd-insert-phase <after> <description>"',
        r'echo "Usage: /prompts:gsd-insert-phase after=<phase-number> description=\"<text>\""',
        out,
    )
    if n5:
        notes.append(f"{cmd}: {n5} echo prompts Usage: strings updated")

    return out, notes


def fix_research_phase_normalization(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    # Update normalization block to support key=value args: phase=...
    # Applies to both prompts and commands versions of research-phase.
    if 'PHASE=$(printf "%02d" "$ARGUMENTS")' not in text:
        return text, notes

    pattern = re.compile(
        r"```bash\n.*?# Normalize phase number.*?\nif \[\[ \"\$ARGUMENTS\" =~ \^\[0-9\]\+\$ \]\]; then\n\s+PHASE=\$\(printf \"%02d\" \"\$ARGUMENTS\"\)\n.*?PHASE=\"\$ARGUMENTS\"\nfi\n\n(?P<grep>grep -A5 \"Phase \${PHASE}:\" \.planning/ROADMAP\.md 2>/dev/null)\n```",
        re.DOTALL,
    )

    def repl(m: re.Match[str]) -> str:
        grep_line = m.group("grep")
        return (
            "```bash\n"
            "# Extract phase from key=value args (phase=...) if present.\n"
            'PHASE_RAW="$ARGUMENTS"\n'
            "for tok in $ARGUMENTS; do\n"
            '  case "$tok" in\n'
            '    phase=*) PHASE_RAW="${tok#phase=}" ;;\n'
            "  esac\n"
            "done\n"
            'PHASE_RAW="${PHASE_RAW#\\"}"; PHASE_RAW="${PHASE_RAW%\\"}"\n'
            'PHASE_RAW="${PHASE_RAW#\\\'}"; PHASE_RAW="${PHASE_RAW%\\\'}"\n'
            "\n"
            "# Normalize phase number (8 -> 08, but preserve decimals like 2.1 -> 02.1)\n"
            'if [[ "$PHASE_RAW" =~ ^[0-9]+$ ]]; then\n'
            '  PHASE=$(printf "%02d" "$PHASE_RAW")\n'
            'elif [[ "$PHASE_RAW" =~ ^([0-9]+)\\.([0-9]+)$ ]]; then\n'
            '  PHASE=$(printf "%02d.%s" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}")\n'
            "else\n"
            '  PHASE="$PHASE_RAW"\n'
            "fi\n"
            "\n"
            f"{grep_line}\n"
            "```"
        )

    out, n = pattern.subn(repl, text)
    if n:
        notes.append(f"research-phase: {n} normalize block updated for phase=")
    return out, notes


def apply_fixes_to_text(text: str, rel_path: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    text2, n = replace_argument_hint(text, rel_path)
    if n:
        notes.extend(n)
    text = text2

    text2, n = fix_research_phase_normalization(text)
    if n:
        notes.extend(n)
    text = text2

    for fn in (
        replace_help_parentheticals,
        replace_plain_todo_and_debug_lines,
        replace_insert_phase,
        replace_description_commands,
        replace_plain_add_commands,
        replace_single_arg_commands,
    ):
        text2, n = fn(text)
        if n:
            notes.extend(n)
        text = text2

    return text, notes


def backup_files(codex_root: Path, files: Iterable[Path], backup_root: Path) -> None:
    for path in files:
        rel = path.relative_to(codex_root)
        dest = backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--codex-root",
        default=str(Path.home() / ".codex"),
        help="Codex root to modify (default: ~/.codex).",
    )
    parser.add_argument(
        "--backup-root",
        default="",
        help="Backup root directory. Default: /tmp/codex-gsd-backup-<timestamp>",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
    args = parser.parse_args()

    codex_root = Path(args.codex_root).expanduser().resolve()
    files = iter_target_files(codex_root)

    if args.backup_root:
        backup_root = Path(args.backup_root).expanduser().resolve()
    else:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        backup_root = Path(tempfile.gettempdir()) / f"codex-gsd-backup-{stamp}"

    if not args.dry_run:
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_files(codex_root, files, backup_root)

    changes: list[Change] = []
    changed_count = 0
    for path in files:
        rel_path = str(path.relative_to(codex_root))
        raw = path.read_text(encoding="utf-8", errors="replace")
        updated, notes = apply_fixes_to_text(raw, rel_path)
        if updated != raw:
            changed_count += 1
            if not args.dry_run:
                path.write_text(updated, encoding="utf-8")
            changes.append(Change(rel_path=rel_path, changed=True, notes=notes))
        else:
            changes.append(Change(rel_path=rel_path, changed=False, notes=[]))

    # Summary to stdout for traceability.
    sys.stdout.write(f"Codex root: {codex_root}\n")
    sys.stdout.write(f"Files scanned: {len(files)}\n")
    if args.dry_run:
        sys.stdout.write(f"Dry run: would change {changed_count} files\n")
    else:
        sys.stdout.write(f"Backup: {backup_root}\n")
        sys.stdout.write(f"Changed files: {changed_count}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
