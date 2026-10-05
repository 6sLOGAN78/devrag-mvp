"""Fixture self-tests for check_pickle.py. Payload source is assembled in strings only, never executed."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_pickle.py"
pytestmark = pytest.mark.unit


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60, check=False)


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


BAD = [
    "import pickle\nx = pickle.loads(b'')\n",
    "import pickle\nx = pickle.load(open('f', 'rb'))\n",
    "import cPickle\n",
    "import dill\nx = dill.loads(b'')\n",
    "import cloudpickle\n",
    "import joblib\nx = joblib.load('f')\n",
    "import pandas as pd\nx = pd.read_pickle('f')\n",
    "import numpy as np\nx = np.load('f', allow_pickle=True)\n",
    "import shelve\nx = shelve.open('f')\n",
    "import marshal\nx = marshal.loads(b'')\n",
    "from pickle import loads\n",
    "import pickle as pk\nx = pk.loads(b'')\n",
]


@pytest.mark.parametrize("body", BAD)
def test_bad_constructs_fail_in_production(tmp_path: Path, body: str) -> None:
    put(tmp_path, "api/x.py", body)
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "api/x.py:" in r.stdout


def test_numpy_load_without_allow_pickle_passes(tmp_path: Path) -> None:
    put(tmp_path, "api/x.py", "import numpy as np\nx = np.load('f')\ny = np.load('f', allow_pickle=False)\n")
    assert run(tmp_path).returncode == 0


def test_pickle_dumps_alone_passes(tmp_path: Path) -> None:
    put(tmp_path, "api/x.py", "import pickle\nx = pickle.dumps(1)\n")
    assert run(tmp_path).returncode == 0


def test_test_tree_requires_gate_ok(tmp_path: Path) -> None:
    put(tmp_path, "test/test_x.py", "import pickle\nx = pickle.loads(b'')\n")
    assert run(tmp_path).returncode == 1
    put(tmp_path, "test/test_x.py", "import pickle\nx = pickle.loads(b'')  # gate-ok: regression fixture built in-test\n")
    assert run(tmp_path).returncode == 0


def test_gate_ok_is_ignored_in_production(tmp_path: Path) -> None:
    put(tmp_path, "api/x.py", "import pickle\nx = pickle.loads(b'')  # gate-ok: nope\n")
    assert run(tmp_path).returncode == 1


def test_skips_when_tree_absent(tmp_path: Path) -> None:
    r = run(tmp_path)
    assert r.returncode == 0
    assert "skipped: tree absent" in r.stdout


def test_unpickler_subclass_fails(tmp_path: Path) -> None:
    put(tmp_path, "api/x.py", "import pickle\n\nclass R(pickle.Unpickler):\n    pass\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "api/x.py:3" in r.stdout
