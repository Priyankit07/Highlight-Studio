"""
Runtime environment and tool detection utilities.
Ensures JS runtimes (deno or node >= 22) are discoverable on PATH for yt-dlp and runner subprocesses.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Standard candidate paths where deno, node, or homebrew packages live
CANDIDATE_PATHS = [
    str(Path.home() / ".deno" / "bin"),
    str(Path.home() / ".local" / "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
]


def _get_executable_version(exe_path: str, runtime_name: str) -> str | None:
    """Run --version on executable and extract semantic version string."""
    try:
        out = subprocess.check_output([exe_path, "--version"], text=True, stderr=subprocess.STDOUT, timeout=3).strip()
        first_line = out.splitlines()[0] if out.splitlines() else ""
        if runtime_name == "deno":
            m = re.search(r"deno\s+([\d\.]+)", first_line)
            return m.group(1) if m else first_line
        elif runtime_name == "node":
            m = re.search(r"v?(\d+\.\d+\.\d+)", first_line)
            return m.group(1) if m else first_line
        return first_line
    except Exception as e:
        logger.debug("Failed to get version for %s (%s): %s", runtime_name, exe_path, e)
        return None


def _is_valid_js_runtime(exe_path: str, runtime_name: str) -> tuple[bool, str | None]:
    """
    Validate that runtime executable meets requirements:
    - deno: any modern version
    - node: major version >= 22
    """
    ver = _get_executable_version(exe_path, runtime_name)
    if not ver:
        return False, None

    if runtime_name == "deno":
        return True, ver

    if runtime_name == "node":
        m = re.match(r"^(\d+)", ver)
        if m:
            major = int(m.group(1))
            if major >= 22:
                return True, ver
            else:
                logger.debug("Node.js found at %s is version %s (< 22); requires >= 22 for yt-dlp challenge solving.", exe_path, ver)
                return False, ver
        return False, ver

    return False, None


def ensure_js_runtime_on_path() -> tuple[str | None, str | None, str | None]:
    """
    Check if deno or node (>=22) is on PATH. If not, inspect common candidate locations
    and prepend to os.environ["PATH"] if found.

    Returns:
        tuple (runtime_name, executable_path, version) or (None, None, None) if not found.
    """
    # Ensure candidate paths are in PATH
    current_path = os.environ.get("PATH", "")
    for cand in CANDIDATE_PATHS:
        cand_p = Path(cand)
        if cand_p.is_dir() and cand not in current_path.split(":"):
            os.environ["PATH"] = f"{cand}:{os.environ.get('PATH', '')}"

    # Search for deno first
    deno_exe = shutil.which("deno")
    if deno_exe:
        valid, ver = _is_valid_js_runtime(deno_exe, "deno")
        if valid:
            return "deno", deno_exe, ver

    # Search candidate paths directly for deno
    for cand in CANDIDATE_PATHS:
        target = Path(cand) / "deno"
        if target.is_file() and os.access(target, os.X_OK):
            valid, ver = _is_valid_js_runtime(str(target), "deno")
            if valid:
                return "deno", str(target), ver

    # Fallback to node (>= 22)
    node_exe = shutil.which("node")
    if node_exe:
        valid, ver = _is_valid_js_runtime(node_exe, "node")
        if valid:
            return "node", node_exe, ver

    # Search candidate paths directly for node
    for cand in CANDIDATE_PATHS:
        target = Path(cand) / "node"
        if target.is_file() and os.access(target, os.X_OK):
            valid, ver = _is_valid_js_runtime(str(target), "node")
            if valid:
                return "node", str(target), ver

    return None, None, None


def is_ejs_installed() -> bool:
    """Check whether yt-dlp-ejs package is installed."""
    try:
        import yt_dlp_ejs
        return True
    except ImportError:
        return False


def get_js_runtime_config() -> dict[str, Any]:
    """Return dictionary suitable for yt_dlp's js_runtimes option."""
    res = ensure_js_runtime_on_path()
    rt_name = res[0] if len(res) > 0 else None
    rt_path = res[1] if len(res) > 1 else None
    if rt_name and rt_path:
        return {rt_name: {"path": rt_path}}
    return {}


def check_js_runtime() -> dict[str, Any]:
    """
    Inspect JS runtime and yt-dlp-ejs availability and return diagnostics dictionary.
    Logs a warning if no JS runtime is found.
    """
    res = ensure_js_runtime_on_path()
    rt_name = res[0] if len(res) > 0 else None
    rt_path = res[1] if len(res) > 1 else None
    ver = res[2] if len(res) > 2 else None
    ejs_ok = is_ejs_installed()

    if rt_name:
        return {
            "available": True,
            "runtime": rt_name,
            "version": ver,
            "path": rt_path,
            "ejs_installed": ejs_ok,
            "warning": None,
        }
    else:
        warning_msg = (
            "No JavaScript runtime (deno or node >= 22) found on PATH. "
            "YouTube URL downloads may fail bot checks or JavaScript challenge solving."
        )
        logger.warning(warning_msg)
        return {
            "available": False,
            "runtime": None,
            "version": None,
            "path": None,
            "ejs_installed": ejs_ok,
            "warning": warning_msg,
        }
