"""launchd LaunchAgent helpers for periodic unattended cleanup."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from mac_cleaner.cleaners.registry import all_cleaners, filter_cleaners

LAUNCH_AGENT_LABEL = "com.mac-cleaner.scheduled"
PLIST_FILENAME = f"{LAUNCH_AGENT_LABEL}.plist"
LOG_BASENAME = "mac-cleaner-scheduled"
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class SchedulerPaths:
    plist: Path
    stdout_log: Path
    stderr_log: Path


def default_paths() -> SchedulerPaths:
    home = Path.home()
    log_dir = home / "Library" / "Logs"
    return SchedulerPaths(
        plist=home / "Library" / "LaunchAgents" / PLIST_FILENAME,
        stdout_log=log_dir / f"{LOG_BASENAME}.log",
        stderr_log=log_dir / f"{LOG_BASENAME}.err.log",
    )


def resolve_mac_cleaner_argv() -> list[str]:
    """Absolute argv prefix to invoke mac-cleaner."""
    exe = shutil.which("mac-cleaner")
    if exe:
        return [exe]
    return [sys.executable, "-m", "mac_cleaner"]


def sudo_categories() -> list[str]:
    return [c.category for c in all_cleaners() if c.requires_sudo]


def default_scheduled_categories(*, include_sudo: bool) -> tuple[str, ...]:
    if include_sudo:
        return ()
    return tuple(c.category for c in all_cleaners() if not c.requires_sudo)


def build_clean_argv(
    categories: tuple[str, ...] | None,
    *,
    include_sudo: bool,
) -> list[str]:
    argv = [*resolve_mac_cleaner_argv(), "clean", "--execute", "-y"]
    selected = categories if categories else default_scheduled_categories(include_sudo=include_sudo)
    if selected:
        for name in selected:
            argv.extend(["-c", name])
    return argv


def build_plist_data(
    days: int,
    categories: tuple[str, ...] | None,
    *,
    include_sudo: bool,
    paths: SchedulerPaths | None = None,
) -> dict[str, object]:
    if days < 1:
        raise ValueError("days must be at least 1")
    paths = paths or default_paths()
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": build_clean_argv(categories, include_sudo=include_sudo),
        "StartInterval": days * SECONDS_PER_DAY,
        "RunAtLoad": False,
        "StandardOutPath": str(paths.stdout_log),
        "StandardErrorPath": str(paths.stderr_log),
    }


def write_plist(
    days: int,
    categories: tuple[str, ...] | None,
    *,
    include_sudo: bool,
    paths: SchedulerPaths | None = None,
) -> Path:
    paths = paths or default_paths()
    paths.plist.parent.mkdir(parents=True, exist_ok=True)
    data = build_plist_data(days, categories, include_sudo=include_sudo, paths=paths)
    with paths.plist.open("wb") as handle:
        plistlib.dump(data, handle)
    return paths.plist


def read_installed_plist(paths: SchedulerPaths | None = None) -> dict[str, object] | None:
    paths = paths or default_paths()
    if not paths.plist.is_file():
        return None
    with paths.plist.open("rb") as handle:
        return plistlib.load(handle)


def plist_interval_days(data: dict[str, object]) -> int | None:
    interval = data.get("StartInterval")
    if isinstance(interval, int) and interval > 0:
        return interval // SECONDS_PER_DAY
    return None


def _launchctl_uid() -> int:
    return os.getuid()


def _launchctl_domain() -> str:
    return f"gui/{_launchctl_uid()}"


def _run_launchctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def unload_agent(paths: SchedulerPaths | None = None) -> None:
    paths = paths or default_paths()
    domain = _launchctl_domain()
    service = f"{domain}/{LAUNCH_AGENT_LABEL}"
    _run_launchctl(["bootout", domain, str(paths.plist)])
    _run_launchctl(["unload", str(paths.plist)])
    _run_launchctl(["remove", service])


def load_agent(paths: SchedulerPaths | None = None) -> tuple[bool, str]:
    paths = paths or default_paths()
    if not paths.plist.is_file():
        return False, f"plist not found: {paths.plist}"

    unload_agent(paths)

    domain = _launchctl_domain()
    result = _run_launchctl(["bootstrap", domain, str(paths.plist)])
    if result.returncode == 0:
        return True, ""

    legacy = _run_launchctl(["load", "-w", str(paths.plist)])
    if legacy.returncode == 0:
        return True, ""

    detail = (result.stderr or result.stdout or legacy.stderr or legacy.stdout).strip()
    return False, detail or "launchctl failed to load the agent"


def is_agent_loaded(paths: SchedulerPaths | None = None) -> bool:
    paths = paths or default_paths()
    domain = _launchctl_domain()
    result = _run_launchctl(["print", f"{domain}/{LAUNCH_AGENT_LABEL}"])
    if result.returncode == 0:
        return True
    legacy = _run_launchctl(["list"])
    return result.returncode != 0 and LAUNCH_AGENT_LABEL in (legacy.stdout or "")


def install_schedule(
    days: int,
    categories: tuple[str, ...] | None,
    *,
    include_sudo: bool,
    paths: SchedulerPaths | None = None,
) -> tuple[bool, str, Path]:
    paths = paths or default_paths()
    if days < 1:
        return False, "days must be at least 1", paths.plist

    if categories:
        cleaners = filter_cleaners(categories)
        if not cleaners:
            return False, "no matching categories", paths.plist
        if not include_sudo and any(c.requires_sudo for c in cleaners):
            skipped = [c.category for c in cleaners if c.requires_sudo]
            return (
                False,
                f"categories require sudo ({', '.join(skipped)}); "
                "pass --include-sudo or omit them",
                paths.plist,
            )

    write_plist(days, categories, include_sudo=include_sudo, paths=paths)
    ok, msg = load_agent(paths)
    if not ok:
        return False, msg, paths.plist
    return True, "", paths.plist


def uninstall_schedule(paths: SchedulerPaths | None = None) -> tuple[bool, str]:
    paths = paths or default_paths()
    unload_agent(paths)
    if paths.plist.is_file():
        paths.plist.unlink()
    return True, ""


def schedule_status(paths: SchedulerPaths | None = None) -> dict[str, object]:
    paths = paths or default_paths()
    data = read_installed_plist(paths)
    loaded = is_agent_loaded(paths) if data else False
    days = plist_interval_days(data) if data else None
    argv = list(data.get("ProgramArguments") or []) if data else []
    return {
        "installed": data is not None,
        "loaded": loaded,
        "plist_path": paths.plist,
        "days": days,
        "program_arguments": argv,
        "stdout_log": paths.stdout_log,
        "stderr_log": paths.stderr_log,
        "sudo_categories": sudo_categories(),
    }
