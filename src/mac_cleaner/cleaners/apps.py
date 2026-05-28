"""Third-party application cache cleaners."""

from __future__ import annotations

from pathlib import Path

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner
from mac_cleaner.executor import clear_directory, delete_targets, remove_path
from mac_cleaner.scanner import existing_paths, paths_size, targets_from_paths


class AppCachesCleaner(Cleaner):
    category = "app-caches"
    description = "Slack, Discord, Spotify, Zoom caches"

    def _paths(self) -> list[Path]:
        home = Path.home()
        return existing_paths(
            home / "Library/Application Support/Slack/Cache",
            home / "Library/Application Support/Slack/Service Worker/CacheStorage",
            home / "Library/Application Support/discord/Cache",
            home / "Library/Application Support/discord/Code Cache",
            home / "Library/Caches/com.spotify.client",
            home / "Library/Caches/us.zoom.xos",
            home / "Library/Logs/Slack",
            home / "Library/Logs/discord",
        )

    def get_deletion_targets(self) -> list[Path]:
        return targets_from_paths(self._paths())

    def scan(self) -> CleanResult:
        paths = self._paths()
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
        for path in self._paths():
            if path.is_dir():
                ok, msg = clear_directory(path, category=self.category)
            else:
                ok, msg = remove_path(path, category=self.category)
            if not ok:
                errors.append(msg)
        status = CleanStatus.CLEANED if not errors else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if not errors else 0,
            status=status,
            paths=scan.paths,
            message="; ".join(errors[:2]),
        )


class MailCleaner(Cleaner):
    category = "mail"
    description = "Mail app envelope indexes and caches"

    def _paths(self) -> list[Path]:
        home = Path.home()
        mail_root = home / "Library/Mail"
        paths: list[Path] = []
        if mail_root.exists():
            for envelope in mail_root.glob("V*/MailData/Envelope Index"):
                paths.append(envelope)
            for cache in mail_root.glob("V*/MailData/*Cache*"):
                paths.append(cache)
        paths.extend(
            existing_paths(
                home / "Library/Caches/com.apple.mail",
            )
        )
        return paths

    def get_deletion_targets(self) -> list[Path]:
        file_paths = [p for p in self._paths() if p.is_file() or not p.exists()]
        dir_paths = [p for p in self._paths() if p.is_dir()]
        return file_paths + targets_from_paths(dir_paths)

    def scan(self) -> CleanResult:
        paths = self._paths()
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
        ok, msg, reclaimed = delete_targets(self.get_deletion_targets(), category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=reclaimed if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )
