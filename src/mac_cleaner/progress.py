"""Deletion progress tracking for file-level UI updates."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

from rich.progress import Progress, TaskID

_current: ContextVar["DeletionProgress | None"] = ContextVar("deletion_progress", default=None)


def get_deletion_progress() -> DeletionProgress | None:
    return _current.get()


def set_deletion_progress(progress: DeletionProgress | None) -> None:
    _current.set(progress)


class DeletionProgress:
    """Reports each file/command step to a Rich progress bar."""

    def __init__(self, progress: Progress, task_id: TaskID) -> None:
        self._progress = progress
        self._task_id = task_id
        self.category = ""

    def set_category(self, category: str) -> None:
        self.category = category

    def deleting(self, target: Path | str, *, category: str | None = None) -> None:
        cat = category or self.category
        label = _format_target(target)
        self._progress.update(
            self._task_id,
            description=f"[cyan]{cat}[/cyan]  [white]{label}[/white]",
        )

    def advance(self, count: int = 1) -> None:
        self._progress.advance(self._task_id, count)


def _format_target(target: Path | str, max_len: int = 72) -> str:
    text = str(target)
    if len(text) <= max_len:
        return text
    return f"…{text[-(max_len - 1) :]}"
