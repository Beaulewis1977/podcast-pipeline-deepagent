"""Regression tests for scripts/gsd_apply_keyvalue_fixes.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_gsd_fixer_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "gsd_apply_keyvalue_fixes.py"
    spec = importlib.util.spec_from_file_location("gsd_apply_keyvalue_fixes", script_path)
    if spec is None or spec.loader is None:
        msg = f"Unable to load script module from {script_path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_replace_plain_add_commands_expands_usage_backreferences() -> None:
    """Usage replacements should emit command text, not literal backreference tokens."""
    module = _load_gsd_fixer_module()
    source = "Usage: /gsd:add-phase <description>\nUsage: /prompts:gsd-add-todo <description>\n"

    updated, notes = module.replace_plain_add_commands(source)

    assert 'Usage: /gsd:add-phase description="<text>"' in updated
    assert 'Usage: /prompts:gsd-add-todo description="<text>"' in updated
    assert "\\1" not in updated
    assert "\\g<cmd>" not in updated
    assert notes == [
        "add-phase: 1 Usage: lines updated",
        "add-todo: 1 Usage: lines updated",
    ]
