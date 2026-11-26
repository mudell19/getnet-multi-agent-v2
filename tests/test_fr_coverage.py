"""Constitution IX: every functional requirement in the spec has a test named test_fr_NNN_*."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fr_every_requirement_has_a_named_test():
    spec = (ROOT / "specs/001-multi-agent-support/spec.md").read_text()
    required = sorted(set(re.findall(r"\*\*FR-(\d{3})\*\*", spec)))
    covered: set[str] = set()
    for f in (ROOT / "tests").rglob("test_*.py"):
        for name in re.findall(r"def (test_fr_\w+)", f.read_text()):
            covered |= set(re.findall(r"fr_(\d{3})", name))
    missing = [f"FR-{n}" for n in required if n not in covered]
    assert not missing, f"requirements without a test: {missing}"
