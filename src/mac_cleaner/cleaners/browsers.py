"""Browser cache cleaners."""

from __future__ import annotations

from pathlib import Path

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner
from mac_cleaner.executor import clear_directory
from mac_cleaner.scanner import existing_paths, paths_size, targets_from_paths


class BrowserCleaner(Cleaner):
    category = "browsers"
    description = "Safari, Chrome, Firefox, Edge caches"

    def _cache_dirs(self) -> list[Path]:
        home = Path.home()
        return existing_paths(
            home / "Library/Caches/com.apple.Safari",
            home / "Library/Safari/LocalStorage",
            home / "Library/Caches/Google/Chrome",
            home / "Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage",
            home / "Library/Caches/Firefox",
            home / "Library/Caches/com.microsoft.edgemac",
            home / "Library/Application Support/Firefox/Profiles",
        )

    def get_deletion_targets(self) -> list[Path]:
        return targets_from_paths(self._cache_dirs())

    def scan(self) -> CleanResult:
        paths = self._cache_dirs()
        size = paths_size(paths)
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=paths)

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        scan = self.scan()
        if scan.size_bytes == 0:
            return scan
        if dry_run:
            return self._result(
                size_bytes=scan.size_bytes,
                status=CleanStatus.DRY_RUN,
                paths=scan.paths,
            )
        errors: list[str] = []
        for path in self._cache_dirs():
            ok, msg = clear_directory(path, category=self.category) if path.is_dir() else (False, "not a directory")
            if not ok:
                errors.append(f"{path.name}: {msg}")
        status = CleanStatus.CLEANED if not errors else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if not errors else 0,
            status=status,
            paths=scan.paths,
            message="; ".join(errors[:2]),
        )
