"""launchd LaunchAgent helpers for periodic unattended cleanup."""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from mac_cleaner.cleaners.registry import all_cleaners, filter_cleaners

LAUNCH_AGENT_LABEL = "com.mac-cleaner.scheduled"
PLIST_FILENAME = f"{LAUNCH_AGENT_LABEL}.plist"
LOG_BASENAME = "mac-cleaner-scheduled"
SUPPORT_DIRNAME = "mac-cleaner"
INNER_SCRIPT_NAME = "scheduled-inner.sh"
APPLESCRIPT_NAME = "scheduled-run.applescript"
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class SchedulerPaths:
    plist: Path
    stdout_log: Path
    stderr_log: Path
    support_dir: Path
    inner_script: Path
    applescript: Path


def default_paths() -> SchedulerPaths:
    home = Path.home()
    log_dir = home / "Library" / "Logs"
    support_dir = home / "Library" / "Application Support" / SUPPORT_DIRNAME
    return SchedulerPaths(
        plist=home / "Library" / "LaunchAgents" / PLIST_FILENAME,
        stdout_log=log_dir / f"{LOG_BASENAME}.log",
        stderr_log=log_dir / f"{LOG_BASENAME}.err.log",
        support_dir=support_dir,
        inner_script=support_dir / INNER_SCRIPT_NAME,
        applescript=support_dir / APPLESCRIPT_NAME,
    )


def resolve_mac_cleaner_argv() -> list[str]:
    """Absolute argv prefix to invoke mac-cleaner."""
    exe = shutil.which("mac-cleaner")
    if exe:
        return [exe]
    return [sys.executable, "-m", "mac_cleaner"]


def sudo_categories() -> list[str]:
    return [c.category for c in all_cleaners() if c.requires_sudo]


def default_scheduled_categories(*, all_categories: bool) -> tuple[str, ...]:
    if all_categories:
        return ()
    return tuple(c.category for c in all_cleaners() if not c.requires_sudo)


def resolve_command_path(name: str, default: str) -> str:
    return shutil.which(name) or default


def format_sudoers_instructions() -> str:
    """visudo-ready snippet for passwordless sudo used by mac-cleaner."""
    user = os.environ.get("USER") or os.getlogin()
    mac_cleaner = resolve_mac_cleaner_argv()
    exe = mac_cleaner[0] if len(mac_cleaner) == 1 else " ".join(mac_cleaner)
    rm = resolve_command_path("rm", "/bin/rm")
    find = resolve_command_path("find", "/usr/bin/find")
    tmutil = resolve_command_path("tmutil", "/usr/bin/tmutil")
    dropin = "/etc/sudoers.d/mac-cleaner"
    return "\n".join(
        [
            f"# mac-cleaner ({exe})",
            f"# Create: sudo visudo -f {dropin}",
            f"# Permissions: sudo chmod 440 {dropin}",
            f"# Validate: sudo visudo -c",
            f"# Remove: sudo rm {dropin}",
            "",
            f"{user} ALL=(ALL) NOPASSWD: {rm}, {find}, {tmutil}",
            "",
        ]
    )


def build_clean_argv(
    categories: tuple[str, ...] | None,
    *,
    all_categories: bool,
) -> list[str]:
    argv = [*resolve_mac_cleaner_argv(), "clean", "--execute", "-y"]
    selected = categories if categories else default_scheduled_categories(all_categories=all_categories)
    if selected:
        for name in selected:
            argv.extend(["-c", name])
    return argv


def escape_for_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_inner_script_body(clean_argv: list[str], paths: SchedulerPaths) -> str:
    cmd = " ".join(shlex.quote(arg) for arg in clean_argv)
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f'exec >>{shlex.quote(str(paths.stdout_log))} 2>>{shlex.quote(str(paths.stderr_log))}\n'
        f"{cmd}\n"
    )


def write_sudo_wrapper(
    categories: tuple[str, ...] | None,
    *,
    all_categories: bool,
    paths: SchedulerPaths,
) -> None:
    """Write helper scripts that show the macOS admin password dialog each run."""
    clean_argv = build_clean_argv(categories, all_categories=all_categories)
    paths.support_dir.mkdir(parents=True, exist_ok=True)
    paths.inner_script.write_text(
        build_inner_script_body(clean_argv, paths),
        encoding="utf-8",
    )
    paths.inner_script.chmod(0o755)

    inner_path = escape_for_applescript(str(paths.inner_script.resolve()))
    paths.applescript.write_text(
        f'do shell script "{inner_path}" with administrator privileges\n',
        encoding="utf-8",
    )


def remove_sudo_wrapper(paths: SchedulerPaths | None = None) -> None:
    paths = paths or default_paths()
    for target in (paths.inner_script, paths.applescript):
        if target.is_file():
            target.unlink()
    if paths.support_dir.is_dir() and not any(paths.support_dir.iterdir()):
        paths.support_dir.rmdir()


def build_program_arguments(
    categories: tuple[str, ...] | None,
    *,
    admin_prompt: bool,
    all_categories: bool,
    paths: SchedulerPaths | None = None,
) -> list[str]:
    paths = paths or default_paths()
    if admin_prompt:
        return ["/usr/bin/osascript", str(paths.applescript.resolve())]
    return build_clean_argv(categories, all_categories=all_categories)


def prompt_admin_password(*, reason: str) -> tuple[bool, str]:
    """Show the standard macOS administrator password dialog once."""
    message = escape_for_applescript(reason)
    script = f'do shell script "true" with administrator privileges with prompt "{message}"'
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, ""
    detail = (result.stderr or result.stdout or "").strip()
    return False, detail or "administrator password was not provided"


def build_plist_data(
    days: int,
    categories: tuple[str, ...] | None,
    *,
    admin_prompt: bool,
    all_categories: bool,
    paths: SchedulerPaths | None = None,
) -> dict[str, object]:
    if days < 1:
        raise ValueError("days must be at least 1")
    paths = paths or default_paths()
    data: dict[str, object] = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": build_program_arguments(
            categories,
            admin_prompt=admin_prompt,
            all_categories=all_categories,
            paths=paths,
        ),
        "StartInterval": days * SECONDS_PER_DAY,
        "RunAtLoad": False,
        "StandardOutPath": str(paths.stdout_log),
        "StandardErrorPath": str(paths.stderr_log),
    }
    if admin_prompt:
        data["LimitLoadToSessionType"] = "Aqua"
    return data


def write_plist(
    days: int,
    categories: tuple[str, ...] | None,
    *,
    admin_prompt: bool,
    all_categories: bool,
    paths: SchedulerPaths | None = None,
) -> Path:
    paths = paths or default_paths()
    paths.plist.parent.mkdir(parents=True, exist_ok=True)
    if admin_prompt:
        write_sudo_wrapper(categories, all_categories=all_categories, paths=paths)
    else:
        remove_sudo_wrapper(paths)
    data = build_plist_data(
        days,
        categories,
        admin_prompt=admin_prompt,
        all_categories=all_categories,
        paths=paths,
    )
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
    admin_prompt: bool = False,
    unattended_full: bool = False,
    paths: SchedulerPaths | None = None,
) -> tuple[bool, str, Path]:
    paths = paths or default_paths()
    if days < 1:
        return False, "days must be at least 1", paths.plist
    if admin_prompt and unattended_full:
        return False, "use either --include-sudo or --unattended-full, not both", paths.plist

    all_categories = admin_prompt or unattended_full

    if categories:
        cleaners = filter_cleaners(categories)
        if not cleaners:
            return False, "no matching categories", paths.plist
        if not all_categories and any(c.requires_sudo for c in cleaners):
            skipped = [c.category for c in cleaners if c.requires_sudo]
            return (
                False,
                f"categories require sudo ({', '.join(skipped)}); "
                "pass --include-sudo, --unattended-full, or omit them",
                paths.plist,
            )

    if admin_prompt:
        ok, msg = prompt_admin_password(
            reason="mac-cleaner needs your password to run scheduled cleanups with system access.",
        )
        if not ok:
            return False, msg or "administrator password required for --include-sudo", paths.plist

    write_plist(
        days,
        categories,
        admin_prompt=admin_prompt,
        all_categories=all_categories,
        paths=paths,
    )
    ok, msg = load_agent(paths)
    if not ok:
        return False, msg, paths.plist
    return True, "", paths.plist


def uninstall_schedule(paths: SchedulerPaths | None = None) -> tuple[bool, str]:
    paths = paths or default_paths()
    unload_agent(paths)
    if paths.plist.is_file():
        paths.plist.unlink()
    remove_sudo_wrapper(paths)
    return True, ""


def schedule_status(paths: SchedulerPaths | None = None) -> dict[str, object]:
    paths = paths or default_paths()
    data = read_installed_plist(paths)
    loaded = is_agent_loaded(paths) if data else False
    days = plist_interval_days(data) if data else None
    argv = list(data.get("ProgramArguments") or []) if data else []
    uses_admin_prompt = bool(argv) and "osascript" in str(argv[0])
    uses_mac_cleaner = any("mac-cleaner" in str(arg) or "mac_cleaner" in str(arg) for arg in argv)
    unattended_full = uses_mac_cleaner and not uses_admin_prompt and "clean" in argv
    return {
        "installed": data is not None,
        "loaded": loaded,
        "plist_path": paths.plist,
        "days": days,
        "program_arguments": argv,
        "stdout_log": paths.stdout_log,
        "stderr_log": paths.stderr_log,
        "sudo_categories": sudo_categories(),
        "uses_admin_prompt": uses_admin_prompt,
        "unattended_full": unattended_full,
        "wrapper_script": paths.inner_script if paths.inner_script.is_file() else None,
    }
