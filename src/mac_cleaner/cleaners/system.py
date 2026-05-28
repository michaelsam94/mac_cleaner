"""System-level cleaners requiring sudo."""

from __future__ import annotations

from pathlib import Path

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner
from mac_cleaner.executor import run_command, run_sudo_find_delete
from mac_cleaner.scanner import path_size


class SystemCachesCleaner(Cleaner):
    category = "system-caches"
    description = "System /Library/Caches"
    requires_sudo = True

    def _root(self) -> Path:
        return Path("/Library/Caches")

    def _top_level_items(self) -> list[Path]:
        root = self._root()
        if not root.exists():
            return []
        try:
            return sorted(root.iterdir())
        except OSError:
            return []

    def get_deletion_targets(self) -> list[Path]:
        # Bulk sudo rm per top-level folder — never enumerate inner files.
        return []

    def get_command_steps(self) -> list[str]:
        return [f"sudo rm -rf {item}" for item in self._top_level_items()]

    def scan(self) -> CleanResult:
        root = self._root()
        size = path_size(root) if root.exists() else 0
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=[root])

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        scan = self.scan()
        items = self._top_level_items()
        if scan.size_bytes == 0 or not items:
            return self._result(size_bytes=0, status=CleanStatus.SKIPPED)
        if dry_run:
            return self._result(
                size_bytes=scan.size_bytes,
                status=CleanStatus.DRY_RUN,
                paths=[str(p) for p in items[:20]],
            )

        errors: list[str] = []
        for item in items:
            ok, msg = run_command(
                ["rm", "-rf", str(item)],
                sudo=True,
                timeout=180,
                category=self.category,
                label=str(item),
            )
            if not ok:
                errors.append(f"{item.name}: {msg}")

        ok = len(errors) < len(items)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=[str(p) for p in items[:20]],
            message="; ".join(errors[:3]),
        )


class SystemLogsCleaner(Cleaner):
    category = "system-logs"
    description = "Rotated system logs"
    requires_sudo = True

    _NAME_PATTERNS = ("*.gz", "*.bz2", "*.xz", "*.old", "*.1", "*.2", "*.3")

    def _rotated_logs(self) -> list[Path]:
        root = Path("/private/var/log")
        if not root.exists():
            return []
        logs: list[Path] = []
        for pattern in self._NAME_PATTERNS:
            logs.extend(root.rglob(pattern))
        return logs

    def get_deletion_targets(self) -> list[Path]:
        return []

    def get_command_steps(self) -> list[str]:
        logs = self._rotated_logs()
        if not logs:
            return []
        return [f"sudo batch delete {len(logs)} rotated log file(s)"]

    def scan(self) -> CleanResult:
        logs = self._rotated_logs()
        size = sum(path_size(p) for p in logs)
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=logs[:20])

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        logs = self._rotated_logs()
        size = sum(path_size(p) for p in logs)
        if size == 0:
            return self._result(size_bytes=0, status=CleanStatus.SKIPPED)
        if dry_run:
            return self._result(size_bytes=size, status=CleanStatus.DRY_RUN, paths=logs[:20])

        ok, msg = run_sudo_find_delete(
            root=Path("/private/var/log"),
            name_patterns=list(self._NAME_PATTERNS),
            category=self.category,
            label="rotated system logs",
        )
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=size if ok else 0,
            status=status,
            paths=logs[:20],
            message=msg,
        )


class SnapshotsCleaner(Cleaner):
    category = "snapshots"
    description = "Local Time Machine snapshots"
    requires_sudo = True

    def _list_snapshots(self) -> list[str]:
        ok, output = run_command(["tmutil", "listlocalsnapshots", "/"], sudo=False)
        if not ok:
            return []
        return [
            line.strip().split()[-1]
            for line in output.splitlines()
            if "com.apple.TimeMachine" in line
        ]

    def get_deletion_targets(self) -> list[Path]:
        return []

    def get_command_steps(self) -> list[str]:
        return [f"tmutil deletelocalsnapshots {name}" for name in self._list_snapshots()]

    def scan(self) -> CleanResult:
        snapshots = self._list_snapshots()
        size = len(snapshots) * 500 * 1024 * 1024 if snapshots else 0
        status = CleanStatus.READY if snapshots else CleanStatus.SKIPPED
        message = f"{len(snapshots)} snapshot(s)" if snapshots else ""
        return self._result(
            size_bytes=size,
            status=status,
            paths=[Path("/")],
            message=message,
        )

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        scan = self.scan()
        snapshots = self._list_snapshots()
        if not snapshots:
            return self._result(size_bytes=0, status=CleanStatus.SKIPPED)
        if dry_run:
            return self._result(
                size_bytes=scan.size_bytes,
                status=CleanStatus.DRY_RUN,
                paths=scan.paths,
                message=scan.message,
            )

        errors: list[str] = []
        for snapshot in snapshots:
            ok, msg = run_command(
                ["tmutil", "deletelocalsnapshots", snapshot],
                sudo=True,
                category=self.category,
                label=f"snapshot {snapshot}",
            )
            if not ok:
                errors.append(msg)
        status = CleanStatus.CLEANED if not errors else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if not errors else 0,
            status=status,
            paths=scan.paths,
            message="; ".join(errors[:2]) if errors else f"Removed {len(snapshots)} snapshot(s)",
        )
