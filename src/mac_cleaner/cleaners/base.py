"""Cleaner base types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CleanStatus(str, Enum):
    READY = "ready"
    SKIPPED = "skipped"
    FAILED = "failed"
    CLEANED = "cleaned"
    DRY_RUN = "dry-run"


@dataclass
class CleanResult:
    category: str
    description: str
    size_bytes: int
    status: CleanStatus
    paths: list[str] = field(default_factory=list)
    message: str = ""
    requires_sudo: bool = False

    @property
    def size_human(self) -> str:
        return format_bytes(self.size_bytes)


def format_bytes(num: int) -> str:
    if num <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class Cleaner(ABC):
    category: str
    description: str
    requires_sudo: bool = False

    @abstractmethod
    def scan(self) -> CleanResult:
        raise NotImplementedError

    @abstractmethod
    def clean(self, *, dry_run: bool = True) -> CleanResult:
        raise NotImplementedError

    def get_deletion_targets(self) -> list[Path]:
        """Individual files/dirs that clean() will remove. Override in subclasses."""
        return []

    def get_command_steps(self) -> list[str]:
        """Non-file cleanup steps (shell commands) counted in progress. Override as needed."""
        return []

    def _result(
        self,
        *,
        size_bytes: int,
        status: CleanStatus,
        paths: list[Path | str] | None = None,
        message: str = "",
    ) -> CleanResult:
        return CleanResult(
            category=self.category,
            description=self.description,
            size_bytes=size_bytes,
            status=status,
            paths=[str(p) for p in (paths or [])],
            message=message,
            requires_sudo=self.requires_sudo,
        )
