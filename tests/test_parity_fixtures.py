"""The parity fixtures for dsh-carryon must match what carrycode computes today (design doc §6)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_parity_fixtures.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_parity_fixtures", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_fixtures_are_up_to_date():
    exporter = load_exporter()
    for name, text in exporter.render_all().items():
        path = exporter.OUT_DIR / name
        assert path.is_file(), f"missing {path}; run scripts/export_parity_fixtures.py"
        assert path.read_text() == text, f"{name} is out of date; run scripts/export_parity_fixtures.py"


def test_every_case_is_well_formed():
    exporter = load_exporter()
    for build in exporter.MODULES.values():
        cases = build()
        names = [(c["op"], c["name"]) for c in cases]
        assert len(names) == len(set(names)), "case names must be unique per op"
        for c in cases:
            assert set(c) == {"op", "name", "input", "expected"}
