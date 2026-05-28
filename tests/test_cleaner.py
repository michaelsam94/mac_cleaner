from mac_cleaner.cleaners.base import format_bytes
from mac_cleaner.cleaners.registry import all_cleaners, filter_cleaners, list_categories
from mac_cleaner.executor import docker_daemon_running, is_writable_path
from mac_cleaner.cleaners.user import TempCleaner
from pathlib import Path


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1024 * 1024 * 5) == "5.0 MB"


def test_all_cleaners_have_unique_categories():
    categories = list_categories()
    assert len(categories) == len(set(categories))


def test_filter_cleaners():
    filtered = filter_cleaners(("xcode", "trash"))
    names = {c.category for c in filtered}
    assert names == {"xcode", "trash"}


def test_scan_returns_results():
    cleaners = all_cleaners()
    for cleaner in cleaners:
        result = cleaner.scan()
        assert result.category == cleaner.category
        assert result.size_bytes >= 0


def test_temp_cleaner_skips_duetexpertd():
    cleaner = TempCleaner()
    path = Path("/var/folders/xx/yy/T/duetexpertd")
    assert cleaner._skip_temp_item(path) is True


def test_system_caches_uses_bulk_steps_not_files():
    from mac_cleaner.cleaners.system import SystemCachesCleaner

    cleaner = SystemCachesCleaner()
    assert cleaner.get_deletion_targets() == []
    steps = cleaner.get_command_steps()
    for step in steps:
        assert step.startswith("sudo rm -rf /Library/Caches/")
    assert len(steps) < 500


def test_docker_skips_when_daemon_not_running(monkeypatch):
    from mac_cleaner.cleaners.dev_tools import DockerCleaner

    monkeypatch.setattr("mac_cleaner.cleaners.dev_tools.command_exists", lambda _name: True)
    monkeypatch.setattr("mac_cleaner.cleaners.dev_tools.docker_daemon_running", lambda: False)
    result = DockerCleaner().scan()
    assert result.status.value == "skipped"
    assert "not running" in result.message.lower()
