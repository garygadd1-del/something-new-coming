import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def mask_guard() -> Path:
    manifest = ROOT / "rust_wrappers" / "Cargo.toml"
    subprocess.check_call(
        ["cargo", "test", "--manifest-path", str(manifest), "--offline", "--quiet"],
    )
    subprocess.check_call(
        ["cargo", "build", "--manifest-path", str(manifest), "--offline", "--quiet"],
    )
    binary = ROOT / "rust_wrappers" / "target" / "debug" / "mask_guard"
    assert binary.is_file()
    return binary
