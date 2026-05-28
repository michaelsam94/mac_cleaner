import plistlib
from pathlib import Path

import pytest

from mac_cleaner.scheduler import (
    LAUNCH_AGENT_LABEL,
    build_clean_argv,
    build_plist_data,
    build_program_arguments,
    default_scheduled_categories,
    format_sudoers_instructions,
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
    support = tmp_path / "Application Support" / "mac-cleaner"
    launch_agents.mkdir(parents=True)
    logs.mkdir()
    support.mkdir(parents=True)
    from mac_cleaner.scheduler import SchedulerPaths

    return SchedulerPaths(
        plist=launch_agents / "com.mac-cleaner.scheduled.plist",
        stdout_log=logs / "mac-cleaner-scheduled.log",
        stderr_log=logs / "mac-cleaner-scheduled.err.log",
        support_dir=support,
        inner_script=support / "scheduled-inner.sh",
        applescript=support / "scheduled-run.applescript",
    )


def test_sudo_categories_are_system_only():
    names = set(sudo_categories())
    assert "system-caches" in names
    assert "user-caches" not in names


def test_default_scheduled_categories_excludes_sudo():
    default = set(default_scheduled_categories(all_categories=False))
    assert "xcode" in default
    assert not default.intersection(sudo_categories())


def test_build_clean_argv_includes_execute_and_yes():
    argv = build_clean_argv((), all_categories=False)
    assert "clean" in argv
    assert "--execute" in argv
    assert "-y" in argv


def test_build_clean_argv_adds_category_flags():
    argv = build_clean_argv(("trash", "xcode"), all_categories=False)
    assert argv.count("-c") == 2
    assert "trash" in argv
    assert "xcode" in argv


def test_build_plist_data_interval():
    data = build_plist_data(7, None, admin_prompt=False, all_categories=False)
    assert data["Label"] == LAUNCH_AGENT_LABEL
    assert data["StartInterval"] == 7 * 86_400
    assert data["RunAtLoad"] is False


def test_build_plist_with_sudo_uses_osascript(sched_paths):
    write_plist(7, None, admin_prompt=True, all_categories=True, paths=sched_paths)
    data = build_plist_data(7, None, admin_prompt=True, all_categories=True, paths=sched_paths)
    args = data["ProgramArguments"]
    assert args[0] == "/usr/bin/osascript"
    assert str(sched_paths.applescript.resolve()) in args[1]
    assert data["LimitLoadToSessionType"] == "Aqua"
    assert sched_paths.inner_script.is_file()
    assert "administrator privileges" in sched_paths.applescript.read_text()


def test_build_program_arguments_direct_without_sudo():
    args = build_program_arguments(None, admin_prompt=False, all_categories=False)


def test_build_program_arguments_unattended_full(sched_paths):
    args = build_program_arguments(
        None,
        admin_prompt=False,
        all_categories=True,
        paths=sched_paths,
    )
    assert "clean" in args
    assert args[0] != "/usr/bin/osascript"


def test_format_sudoers_includes_commands():
    text = format_sudoers_instructions()
    assert "NOPASSWD" in text
    assert "/etc/sudoers.d/mac-cleaner" in text
    assert "rm" in text
    assert "find" in text
    assert "tmutil" in text


def test_write_and_read_plist(sched_paths):
    write_plist(3, ("trash",), admin_prompt=False, all_categories=False, paths=sched_paths)
    data = read_installed_plist(sched_paths)
    assert data is not None
    assert plist_interval_days(data) == 3
    args = data["ProgramArguments"]
    assert "-c" in args
    assert "trash" in args


def test_install_rejects_unknown_category(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, msg, _ = install_schedule(7, ("not-a-category",), paths=sched_paths)
    assert not ok
    assert "no matching" in msg.lower()


def test_install_rejects_sudo_category_without_flag(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, msg, _ = install_schedule(7, ("system-caches",), paths=sched_paths)
    assert not ok
    assert "sudo" in msg.lower()


def test_install_with_sudo_requires_admin_prompt(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    monkeypatch.setattr(
        "mac_cleaner.scheduler.prompt_admin_password",
        lambda **_: (False, "cancelled"),
    )
    ok, msg, _ = install_schedule(
        7, None, admin_prompt=True, paths=sched_paths,
    )
    assert not ok
    assert msg


def test_install_rejects_both_sudo_modes(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, msg, _ = install_schedule(
        7,
        None,
        admin_prompt=True,
        unattended_full=True,
        paths=sched_paths,
    )
    assert not ok
    assert "not both" in msg.lower()


def test_install_unattended_full_no_wrapper(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, _, _ = install_schedule(
        7, None, unattended_full=True, paths=sched_paths,
    )
    assert ok
    assert not sched_paths.applescript.exists()
    data = read_installed_plist(sched_paths)
    args = data["ProgramArguments"]
    assert "osascript" not in args[0]
    assert "clean" in args


def test_install_with_sudo_writes_wrapper(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    monkeypatch.setattr(
        "mac_cleaner.scheduler.prompt_admin_password",
        lambda **_: (True, ""),
    )
    ok, _, _ = install_schedule(7, None, admin_prompt=True, paths=sched_paths)
    assert ok
    assert sched_paths.inner_script.is_file()
    assert "clean" in sched_paths.inner_script.read_text()


def test_install_writes_plist(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.load_agent", lambda _paths: (True, ""))
    ok, _, plist = install_schedule(14, None, paths=sched_paths)
    assert ok
    assert plist.is_file()
    with plist.open("rb") as handle:
        data = plistlib.load(handle)
    assert data["StartInterval"] == 14 * 86_400


def test_uninstall_removes_plist(sched_paths, monkeypatch):
    monkeypatch.setattr("mac_cleaner.scheduler.unload_agent", lambda _paths: None)
    write_plist(1, None, admin_prompt=True, all_categories=True, paths=sched_paths)
    uninstall_schedule(sched_paths)
    assert not sched_paths.plist.exists()
    assert not sched_paths.inner_script.exists()


def test_schedule_status_not_installed(sched_paths):
    info = schedule_status(sched_paths)
    assert info["installed"] is False
