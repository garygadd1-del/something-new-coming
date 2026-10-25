"""Process liveness checks. Signal 0 on POSIX only asks whether a pid exists."""

from __future__ import annotations

import os
import sys


def proc_start_unix(pid: int) -> float | None:
    """Return the process creation time as Unix seconds, or None when it cannot be read."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return None
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        ok = kernel.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        kernel.CloseHandle(handle)
        if not ok:
            return None
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return ticks / 1e7 - 11644473600.0
    except (OSError, AttributeError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if sys.platform == "win32":
        return proc_start_unix(pid) is not None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
