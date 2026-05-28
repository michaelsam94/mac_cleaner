"""Developer tool and runtime cleaners."""

from __future__ import annotations

from pathlib import Path

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner
from mac_cleaner.executor import (
    clear_directory,
    clear_directory_children,
    command_exists,
    delete_targets,
    docker_daemon_running,
    force_remove_tree,
    remove_path,
    run_command,
)
from mac_cleaner.scanner import enumerate_deletion_items, existing_paths, path_size, paths_size, targets_from_paths


class XcodeCleaner(Cleaner):
    category = "xcode"
    description = "Xcode DerivedData, Archives, old DeviceSupport"

    def _paths(self) -> list[Path]:
        home = Path.home()
        return existing_paths(
            home / "Library/Developer/Xcode/DerivedData",
            home / "Library/Developer/Xcode/Archives",
            home / "Library/Developer/Xcode/iOS DeviceSupport",
            home / "Library/Developer/Xcode/watchOS DeviceSupport",
            home / "Library/Developer/Xcode/tvOS DeviceSupport",
        )

    def _removable_items(self) -> list[Path]:
        items: list[Path] = []
        for path in self._paths():
            if path.is_dir() and path.name.endswith("DeviceSupport"):
                try:
                    items.extend(path.iterdir())
                except OSError:
                    continue
            elif path.is_dir():
                try:
                    items.extend(path.iterdir())
                except OSError:
                    continue
            else:
                items.append(path)
        return items

    def get_deletion_targets(self) -> list[Path]:
        return self._removable_items()

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
        removed_any = False
        errors: list[str] = []
        for item in self._removable_items():
            ok, msg = force_remove_tree(item, category=self.category)
            if ok:
                removed_any = True
            elif msg:
                errors.append(msg)
        status = CleanStatus.CLEANED if removed_any else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if removed_any else 0,
            status=status,
            paths=scan.paths,
            message="; ".join(errors[:2]),
        )


class SimulatorCleaner(Cleaner):
    category = "simulator"
    description = "CoreSimulator caches and unavailable runtimes"

    def _paths(self) -> list[Path]:
        home = Path.home()
        return existing_paths(
            home / "Library/Developer/CoreSimulator/Caches",
            home / "Library/Developer/CoreSimulator/Temp",
            home / "Library/Logs/CoreSimulator",
        )

    def get_deletion_targets(self) -> list[Path]:
        return targets_from_paths(self._paths())

    def get_command_steps(self) -> list[str]:
        if command_exists("xcrun"):
            return ["xcrun simctl delete unavailable"]
        return []

    def scan(self) -> CleanResult:
        paths = self._paths()
        size = paths_size(paths)
        status = CleanStatus.READY if size > 0 else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=paths)

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        scan = self.scan()
        if scan.size_bytes == 0 and not command_exists("xcrun"):
            return self._result(size_bytes=0, status=CleanStatus.SKIPPED, message="xcrun not installed")
        if dry_run:
            extra = 100 * 1024 * 1024 if command_exists("xcrun") else 0
            return self._result(
                size_bytes=scan.size_bytes + extra,
                status=CleanStatus.DRY_RUN if scan.size_bytes or command_exists("xcrun") else CleanStatus.SKIPPED,
                paths=scan.paths,
            )

        errors: list[str] = []
        for path in self._paths():
            ok, msg = clear_directory(path, category=self.category)
            if not ok:
                errors.append(msg)
        if command_exists("xcrun"):
            ok, msg = run_command(
                ["xcrun", "simctl", "delete", "unavailable"],
                category=self.category,
            )
            if not ok and "No devices" not in msg:
                errors.append(msg)
        status = CleanStatus.CLEANED if not errors else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if not errors else 0,
            status=status,
            paths=scan.paths,
            message="; ".join(errors[:2]),
        )


class DockerCleaner(Cleaner):
    category = "docker"
    description = "Docker images, containers, volumes"

    def get_command_steps(self) -> list[str]:
        if command_exists("docker") and docker_daemon_running():
            return ["docker system prune -af --volumes"]
        return []

    def scan(self) -> CleanResult:
        if not command_exists("docker"):
            return self._result(
                size_bytes=0,
                status=CleanStatus.SKIPPED,
                message="docker not installed",
            )
        if not docker_daemon_running():
            return self._result(
                size_bytes=0,
                status=CleanStatus.SKIPPED,
                message="Docker is not running — start Docker Desktop and retry",
            )
        ok, output = run_command(["docker", "system", "df", "--format", "{{.Size}}"])
        if not ok:
            return self._result(size_bytes=0, status=CleanStatus.SKIPPED, message=output)
        docker_dir = Path.home() / "Library/Containers/com.docker.docker"
        size = path_size(docker_dir) if docker_dir.exists() else 0
        status = CleanStatus.READY if size > 0 or self.get_command_steps() else CleanStatus.SKIPPED
        return self._result(size_bytes=size, status=status, paths=[docker_dir])

    def clean(self, *, dry_run: bool = True) -> CleanResult:
        scan = self.scan()
        if scan.status == CleanStatus.SKIPPED:
            return scan
        if dry_run:
            return self._result(
                size_bytes=scan.size_bytes,
                status=CleanStatus.DRY_RUN,
                paths=scan.paths,
            )
        if not docker_daemon_running():
            return self._result(
                size_bytes=0,
                status=CleanStatus.SKIPPED,
                message="Docker is not running — start Docker Desktop and retry",
            )
        ok, msg = run_command(
            ["docker", "system", "prune", "-af", "--volumes"],
            category=self.category,
        )
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )


class DevCachesCleaner(Cleaner):
    category = "dev-caches"
    description = "Gradle, Maven, CocoaPods, Flutter caches"

    def _paths(self) -> list[Path]:
        home = Path.home()
        return existing_paths(
            home / ".gradle/caches",
            home / ".m2/repository",
            home / "Library/Caches/CocoaPods",
            home / ".cocoapods",
            home / ".flutter",
            home / "Library/Caches/flutter",
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
        ok, msg, _ = delete_targets(self.get_deletion_targets(), category=self.category)
        status = CleanStatus.CLEANED if ok else CleanStatus.FAILED
        return self._result(
            size_bytes=scan.size_bytes if ok else 0,
            status=status,
            paths=scan.paths,
            message=msg,
        )
