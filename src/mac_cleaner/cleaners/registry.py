"""Cleaner registry."""

from __future__ import annotations

from mac_cleaner.cleaners.apps import AppCachesCleaner, MailCleaner
from mac_cleaner.cleaners.base import Cleaner
from mac_cleaner.cleaners.browsers import BrowserCleaner
from mac_cleaner.cleaners.dev_tools import (
    DevCachesCleaner,
    DockerCleaner,
    SimulatorCleaner,
    XcodeCleaner,
)
from mac_cleaner.cleaners.package_managers import (
    cargo_cleaner,
    gem_cleaner,
    homebrew_cleaner,
    npm_cleaner,
    pip_cleaner,
    yarn_cleaner,
)
from mac_cleaner.cleaners.system import (
    SnapshotsCleaner,
    SystemCachesCleaner,
    SystemLogsCleaner,
)
from mac_cleaner.cleaners.user import (
    DsStoreCleaner,
    TempCleaner,
    TrashCleaner,
    UserCachesCleaner,
    UserLogsCleaner,
)


def all_cleaners() -> list[Cleaner]:
    return [
        UserCachesCleaner(),
        UserLogsCleaner(),
        TempCleaner(),
        TrashCleaner(),
        DsStoreCleaner(),
        SystemCachesCleaner(),
        SystemLogsCleaner(),
        SnapshotsCleaner(),
        homebrew_cleaner(),
        npm_cleaner(),
        pip_cleaner(),
        yarn_cleaner(),
        cargo_cleaner(),
        gem_cleaner(),
        XcodeCleaner(),
        SimulatorCleaner(),
        DockerCleaner(),
        DevCachesCleaner(),
        BrowserCleaner(),
        AppCachesCleaner(),
        MailCleaner(),
    ]


def filter_cleaners(categories: tuple[str, ...] | None) -> list[Cleaner]:
    cleaners = all_cleaners()
    if not categories:
        return cleaners
    wanted = {c.lower().strip() for c in categories}
    return [c for c in cleaners if c.category.lower() in wanted]


def list_categories() -> list[str]:
    return [c.category for c in all_cleaners()]
