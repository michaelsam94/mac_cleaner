import plistlib
from pathlib import Path

import pytest

from mac_cleaner.scheduler import (
    LAUNCH_AGENT_LABEL,
    build_clean_argv,
    build_plist_data,
    default_scheduled_categories,
    install_schedule,
    plist_interval_days,
    read_installed_plist,
    schedule_status,
    sudo_categories,
    uninstall_schedule,
    write_plist,
)


@pytest.fixture
def sched_paths(tmp_path: Path):
    launch_agents = tmp_path / "LaunchAgents"
    logs = tmp_path / "Logs"
    launch_agents.mkdir()
    logs.mkdir()
    from mac_cleaner.scheduler import SchedulerPaths

    return SchedulerPaths(
        plist=launch_agents / "com.mac-cleaner.scheduled.plist",
        stdout_log=logs / "mac-cleaner-scheduled.log",
        stderr_log=logs / "mac-cleaner-scheduled.err.log",
    )


def test_sudo_categories_are_system_only():
    names = set(sudo_categories())
    assert "system-caches" in names
    assert "user-caches" not in names


def test_default_scheduled_categories_excludes_sudo():
    default = set(default_scheduled_categories(include_sudo=False))
    assert "xcode" in default
    assert not default.intersection(sudo_categories())


def test_build_clean_argv_includes_execute_and_yes():
    argv = build_clean_argv((), include_sudo=False)
    assert "clean" in argv
    assert "--execute" in argv
    assert "-y" in argv


def test_build_clean_argv_adds_category_flags():
    argv = build_clean_argv(("trash", "xcode"), include_sudo=False)
    assert argv.count("-c") == 2
    assert "trash" in argv
    assert "xcode" in argv


def test_build_plist_data_interval():
    data = build_plist_data(7, None, include_sudo=False)
    assert data["Label"] == LAUNCH_AGENT_LABEL
    assert data["StartInterval"] == 7 * 86_400
    assert data["RunAtLoad"] is False


def test_write_and_read_plist(sched_paths):
    write_plist(3, ("trash",), include_sudo=False, paths=sched_paths)
    data = read_installed_plist(sched_paths)
    assert data is not None
    assert plist_interval_days(data) == 3
    args = data["ProgramArguments"]
    assert "-c" in args
    assert "trash" in args


def test_install_rejects_unknown_category(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, msg, _ = install_schedule(7, ("not-a-category",), include_sudo=False, paths=sched_paths)
    assert not ok
    assert "no matching" in msg.lower()


def test_install_rejects_sudo_category_without_flag(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, msg, _ = install_schedule(
        7,
        ("system-caches",),
        include_sudo=False,
        paths=sched_paths,
    )
    assert not ok
    assert "sudo" in msg.lower()


def test_install_writes_plist(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, _, plist = install_schedule(14, None, include_sudo=False, paths=sched_paths)
    assert ok
    assert plist.is_file()
    with plist.open("rb") as handle:
        data = plistlib.load(handle)
    assert data["StartInterval"] == 14 * 86_400


def test_uninstall_removes_plist(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.unload_agent", lambda _paths: None)
    write_plist(1, None, include_sudo=False, paths=sched_paths)
    uninstall_schedule(sched_paths)
    assert not sched_paths.plist.exists()


def test_schedule_status_not_installed(sched_paths):
    info = schedule_status(sched_paths)
    assert info["installed"] is False
