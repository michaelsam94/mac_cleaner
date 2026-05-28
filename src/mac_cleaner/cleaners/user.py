"""User-owned cache and log cleaners."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner
from mac_cleaner.executor import (
    clear_directory,
    clear_directory_children,
    delete_targets,
    force_remove_tree,
    is_writable_path,
    remove_path,
)
from mac_cleaner.scanner import (
    enumerate_deletion_items,
    existing_paths,
    path_size,
    paths_size,
    targets_from_paths,
)


class UserCachesCleaner(Cleaner):
    category = "user-caches"
    description = "User Library caches"

    def _root(self) -> Path:
        return Path.home() / "Library" / "Caches"

    def get_deletion_targets(self) -> list[Path]:
        root = self._root()
        if not root.is_dir():
            return []
        try:
            return sorted(root.iterdir())
        except OSError:
            return []

    def scan(self) -> CleanResult:
        root = self._root()
        size = path_size(root) if root.exists() else 0
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=[root])

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
        ok, msg, _removed, _skipped = clear_directory_children(
            self._root(),
            category=self.category,
        )
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )


class UserLogsCleaner(Cleaner):
    category = "user-logs"
    description = "User Library logs"

    def _root(self) -> Path:
        return Path.home() / "Library" / "Logs"

    def get_deletion_targets(self) -> list[Path]:
        root = self._root()
        return targets_from_paths([root], contents_only=True) if root.exists() else []

    def scan(self) -> CleanResult:
        root = self._root()
        size = path_size(root) if root.exists() else 0
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=[root])

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
        ok, msg = clear_directory(self._root(), category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )


class TrashCleaner(Cleaner):
    category = "trash"
    description = "User Trash"

    def _root(self) -> Path:
        return Path.home() / ".Trash"

    def get_deletion_targets(self) -> list[Path]:
        root = self._root()
        return targets_from_paths([root], contents_only=True) if root.exists() else []

    def scan(self) -> CleanResult:
        root = self._root()
        size = path_size(root) if root.exists() else 0
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=[root])

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
        ok, msg = clear_directory(self._root(), category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )


class DsStoreCleaner(Cleaner):
    category = "ds-store"
    description = ".DS_Store files under home"

    def _find_files(self) -> list[Path]:
        home = str(Path.home())
        try:
            result = subprocess.run(
                [
                    "find",
                    home,
                    "-name",
                    ".DS_Store",
                    "-not",
                    "-path",
                    "*/Library/Application Support/MobileSync/*",
                    "-maxdepth",
                    "8",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                return []
            return [Path(line) for line in result.stdout.splitlines() if line.strip()]
        except subprocess.SubprocessError:
            return []

    def get_deletion_targets(self) -> list[Path]:
        return self._find_files()

    def scan(self) -> CleanResult:
        files = self._find_files()
        size = paths_size(files)
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=files[:20])

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        files = self._find_files()
        size = paths_size(files)
        if size == 0:
            return self._result(size_bytes=0, status=CleanStatus.SKIPPED)
        if dry_run:
            return self._result(size_bytes=size, status=CleanStatus.DRY_RUN, paths=files[:20])

        ok, msg, reclaimed = delete_targets(files, category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=reclaimed if ok else 0,
            status=status,
            paths=files[:20],
            message=msg,
        )


class TempCleaner(Cleaner):
    category = "temp"
    description = "Temporary files (/tmp and user temp)"

    _PROTECTED_PREFIXES = ("com.apple.",)
    _PROTECTED_NAMES = frozenset({
        "duetexpertd",
        "powerlog",
        "TemporaryItems",
    })

    def _skip_temp_item(self, path: Path) -> bool:
        name = path.name
        if any(name.startswith(prefix) for prefix in self._PROTECTED_PREFIXES):
            return True
        if name in self._PROTECTED_NAMES:
            return True
        if "TemporaryItems" in path.parts:
            return True
        if not is_writable_path(path):
            return True
        if path.is_dir():
            try:
                path.iterdir().__next__()
            except StopIteration:
                return False
            except OSError:
                return True
        return False

    def _temp_paths(self) -> list[Path]:
        candidates: list[Path] = [Path("/tmp")]
        tmpdir = os.environ.get("TMPDIR")
        if tmpdir:
            candidates.append(Path(tmpdir))

        seen: set[str] = set()
        unique: list[Path] = []
        for path in candidates:
            if not is_writable_path(path):
                continue
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    def get_deletion_targets(self) -> list[Path]:
        items: list[Path] = []
        for root in self._temp_paths():
            if not root.is_dir():
                if not self._skip_temp_item(root):
                    items.append(root)
                continue
            try:
                for child in root.iterdir():
                    if not self._skip_temp_item(child):
                        items.append(child)
            except OSError:
                continue
        return items

    def scan(self) -> CleanResult:
        paths = self._temp_paths()
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
        removed_any = False
        for path in self._temp_paths():
            if path.is_dir():
                ok, msg, removed, _skipped = clear_directory_children(
                    path,
                    category=self.category,
                    skip=self._skip_temp_item,
                )
            else:
                ok, msg = force_remove_tree(path, category=self.category)
                removed = 1 if ok else 0
            if removed:
                removed_any = True
            if msg:
                errors.append(msg)
        status = CleanStatus.CLEANED if removed_any else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if removed_any else 0,
            status=status,
            paths=scan.paths,
            message="; ".join(errors[:2]),
        )
