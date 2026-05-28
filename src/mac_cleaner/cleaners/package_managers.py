"""Package manager cache cleaners."""

from __future__ import annotations

from pathlib import Path

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner
from mac_cleaner.executor import command_exists, delete_targets, run_command
from mac_cleaner.scanner import existing_paths, path_size, paths_size, targets_from_paths


class CommandCacheCleaner(Cleaner):
    """Run a cache-clean command and optionally measure known cache dirs."""

    def __init__(
        self,
        category: str,
        description: str,
        command: list[str],
        cache_dirs: list[Path | str] | None = None,
        check_binary: str | None = None,
    ) -> None:
        self.category = category
        self.description = description
        self._command = command
        self._cache_dirs = cache_dirs or []
        self._check_binary = check_binary or command[0]

    def get_deletion_targets(self) -> list[Path]:
        if not command_exists(self._check_binary):
            return []
        return targets_from_paths(existing_paths(*self._cache_dirs))

    def get_command_steps(self) -> list[str]:
        if not command_exists(self._check_binary):
            return []
        return [" ".join(self._command)]

    def scan(self) -> CleanResult:
        if not command_exists(self._check_binary):
            return self._result(
                size_bytes=0,
                status=CleanStatus.SKIPPED,
                message=f"{self._check_binary} not installed",
            )
        paths = existing_paths(*self._cache_dirs)
        size = paths_size(paths) if paths else 0
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        msg = "" if size > 0 else "cache empty or unknown size"
        return self._result(size_bytes=size, status=status, paths=paths, message=msg)

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        scan = self.scan()
        if scan.status == CleanStatus.SKIPPED and "not installed" in scan.message:
            return scan
        if dry_run:
            return self._result(
                size_bytes=scan.size_bytes,
                status=CleanStatus.DRY_RUN,
                paths=scan.paths,
                message=scan.message,
            )
        targets = self.get_deletion_targets()
        if targets:
            delete_targets(targets, category=self.category)
        ok, msg = run_command(self._command, category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )


def homebrew_cleaner() -> CommandCacheCleaner:
    home = Path.home()
    return CommandCacheCleaner(
        category="homebrew",
        description="Homebrew cache and old versions",
        command=["brew", "cleanup", "-s", "--prune=all"],
        cache_dirs=[
            home / "Library/Caches/Homebrew",
            Path("/opt/homebrew/Cache"),
            Path("/usr/local/Homebrew"),
        ],
        check_binary="brew",
    )


def npm_cleaner() -> CommandCacheCleaner:
    return CommandCacheCleaner(
        category="npm",
        description="npm cache",
        command=["npm", "cache", "clean", "--force"],
        cache_dirs=[Path.home() / ".npm"],
        check_binary="npm",
    )


def pip_cleaner() -> CommandCacheCleaner:
    return CommandCacheCleaner(
        category="pip",
        description="pip cache",
        command=["pip3", "cache", "purge"],
        cache_dirs=[Path.home() / "Library/Caches/pip"],
        check_binary="pip3",
    )


def yarn_cleaner() -> CommandCacheCleaner:
    return CommandCacheCleaner(
        category="yarn",
        description="Yarn cache",
        command=["yarn", "cache", "clean"],
        cache_dirs=[
            Path.home() / "Library/Caches/Yarn",
            Path.home() / ".yarn/cache",
        ],
        check_binary="yarn",
    )


class PathCacheCleaner(Cleaner):
    """Delete known cache directories without running a tool command."""

    def __init__(self, category: str, description: str, cache_dirs: list[Path | str]) -> None:
        self.category = category
        self.description = description
        self._cache_dirs = cache_dirs

    def get_deletion_targets(self) -> list[Path]:
        return targets_from_paths(existing_paths(*self._cache_dirs))

    def scan(self) -> CleanResult:
        paths = existing_paths(*self._cache_dirs)
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
        ok, msg, _ = delete_targets(self.get_deletion_targets(), category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )


def cargo_cleaner() -> PathCacheCleaner:
    home = Path.home()
    return PathCacheCleaner(
        category="cargo",
        description="Rust cargo registry and git cache",
        cache_dirs=[
            home / ".cargo/registry",
            home / ".cargo/git",
        ],
    )


def gem_cleaner() -> CommandCacheCleaner:
    return CommandCacheCleaner(
        category="gem",
        description="Ruby gem cache",
        command=["gem", "cleanup"],
        cache_dirs=[Path.home() / ".gem"],
        check_binary="gem",
    )
