"""SEC-05 regression (R-38): untrusted deserialization is rejected by the gate, not filtered.

The documented RestrictedUnpickler allows any ``numpy*`` global. The gadget test below shows
that allow-list is bypassable by a callable shipped inside numpy. It needs numpy, which is not
in the approved Phase 1 package set; it skips with that reason until a later plan adds numpy
(recorded as B-13). If the pinned numpy ships no string-executing callable the test also skips.
"""
from __future__ import annotations

import builtins
import importlib
import io
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "ci" / "check_pickle.py"
MARKER = "__devrag_gadget_marker__"
GADGET_CANDIDATES = (("numpy.testing._private.utils", "runstring"),)

pytestmark = pytest.mark.unit


def test_gate_rejects_fixture_that_unpickles_bytes(tmp_path: Path) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "x.py").write_text("import pickle\n\ndef load(b):\n    return pickle." + "loads(b)\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(CHECK), "--root", str(tmp_path)], capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 1
    assert "api/x.py:" in r.stdout


def test_real_production_trees_have_no_pickle_findings() -> None:
    r = subprocess.run([sys.executable, str(CHECK), "--root", str(REPO_ROOT)], capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 0, r.stdout


class NumpyAllowListUnpickler(pickle.Unpickler):  # gate-ok: allow-list subclass used only to demonstrate the bypass
    """Mirrors the documented whitelist: any global from a numpy module is allowed."""

    def find_class(self, module: str, name: str):
        if module.startswith("numpy"):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"global {module}.{name} is forbidden")


def _find_gadget():
    for module_name, attr in GADGET_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        func = getattr(module, attr, None)
        if func is not None:
            return module_name, attr, func
    return None


def test_numpy_allow_list_unpickler_is_bypassable() -> None:
    pytest.importorskip("numpy", reason="numpy is not in the approved Phase 1 package set (B-13)")
    found = _find_gadget()
    if found is None:
        pytest.skip("pinned numpy ships no string-executing callable (runstring)")
    _module_name, _attr, func = found
    # The payload only sets a marker attribute on builtins; it records execution and does nothing else.
    code = f"import builtins; builtins.{MARKER} = True"

    class Payload:
        def __reduce__(self):
            return func, (code, {})

    blob = pickle.dumps(Payload())
    assert not hasattr(builtins, MARKER)
    try:
        NumpyAllowListUnpickler(io.BytesIO(blob)).load()  # gate-ok: regression fixture built in-test
        assert getattr(builtins, MARKER, False) is True, "allow-list unpickler did not execute the numpy gadget"
    finally:
        if hasattr(builtins, MARKER):
            delattr(builtins, MARKER)
