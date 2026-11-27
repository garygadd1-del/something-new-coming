import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "amd_gpu_sampler"
POLLER = ROOT / "poller.ps1"

FORBIDDEN = [
    r"shell\s*=\s*True",
    r"os\.remove\b",
    r"os\.unlink\b",
    r"shutil\.rmtree",
    r"\.unlink\(",
    r"Remove-Item",
    r"Invoke-WebRequest",
    r"Invoke-RestMethod",
    r"Invoke-Expression",
    r"\burllib\b",
    r"import requests",
    r"import socket",
    r"\bsocket\.",
    r"taskkill",
    r"Stop-Process",
    r"\bADL",
    r"atiadl",
    r"\beval\(",
    r"\bexec\(",
    r"DownloadString",
    r"subprocess\.run\b",
    r"subprocess\.call\b",
]


def _sources():
    files = list(PACKAGE.glob("*.py")) + [POLLER]
    return [(path, path.read_text(encoding="utf-8")) for path in files]


def test_package_stays_inside_the_read_only_contract():
    for path, text in _sources():
        for pattern in FORBIDDEN:
            assert re.search(pattern, text) is None, f"{path.name} matched {pattern}"


def test_posix_pid_probe_is_signal_zero_only():
    text = (PACKAGE / "process_info.py").read_text(encoding="utf-8")
    assert "os.kill(pid, 0)" in text
    assert "os.kill" not in text.replace("os.kill(pid, 0)", "")


def test_poller_publishes_the_gpu_state_contract():
    text = POLLER.read_text(encoding="utf-8")
    for needle in (
        "gpu_state/1",
        "util_pct",
        "vram_used_gb",
        "vram_used_mb",
        "temp_c",
        "core_temp_c",
        "temp_source",
        "reporting_paused",
        "pause_reason",
        "thermal_pause_c",
        "thermal_resume_c",
        "LibreHardwareMonitor",
        "win-perfcounters",
        "STOP",
        "engtype_3d",
        "engtype_compute",
        "Dedicated Usage",
        "ThermalPauseC = 78",
        "ThermalResumeC = 75",
        "IncludeJunction",
        "RX 7900 -> RX 79xx",
        "process left running",
    ):
        assert needle in text
