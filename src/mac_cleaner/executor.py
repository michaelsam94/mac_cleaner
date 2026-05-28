"""File deletion and command execution."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

from mac_cleaner.progress import get_deletion_progress
from mac_cleaner.scanner import enumerate_deletion_items

_sudo_ready = False


def is_writable_path(path: Path) -> bool:
    """True if the path exists and the current user can read/write it."""
    try:
        if not path.exists():
            return False
        if path.is_dir():
            return os.access(path, os.R_OK | os.W_OK | os.X_OK)
        return os.access(path, os.R_OK | os.W_OK)
    except OSError:
        return False


def ensure_sudo() -> tuple[bool, str]:
    """Prompt once for the administrator password and cache sudo credentials."""
    global _sudo_ready
    if _sudo_ready:
        return True, ""

    progress = get_deletion_progress()
    if progress:
        progress.deleting("[sudo] waiting for administrator password...")

    try:
        result = subprocess.run(
            ["sudo", "-v"],
            check=False,
        )
    except subprocess.SubprocessError as exc:
        if progress:
            progress.advance()
        return False, str(exc)

    if progress:
        progress.advance()

    if result.returncode != 0:
        return False, "sudo authentication failed or was cancelled"

    _sudo_ready = True
    return True, ""


def force_remove_tree(path: Path, *, category: str = "") -> tuple[bool, str]:
    """Remove a file or directory tree; return gracefully on permission errors."""
    if not path.exists():
        return True, ""

    progress = get_deletion_progress()
    if progress:
        progress.deleting(path, category=category)

    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        if progress:
            progress.advance()
        return True, ""
    except (PermissionError, OSError) as exc:
        if progress:
            progress.advance()
        return False, str(exc)


def clear_directory_children(
    path: Path,
    *,
    category: str = "",
    skip: Callable[[Path], bool] | None = None,
) -> tuple[bool, str, int, int]:
    """
    Remove each top-level child with rmtree.
    Returns (success, message, removed_count, skipped_count).
    """
    if not path.exists() or not path.is_dir():
        ok, msg = force_remove_tree(path, category=category)
        return ok, msg, (1 if ok else 0), (0 if ok else 1)

    removed = 0
    skipped = 0
    errors: list[str] = []

    try:
        children = list(path.iterdir())
    except OSError as exc:
        return False, str(exc), 0, 1

    for child in children:
        if skip and skip(child):
            skipped += 1
            progress = get_deletion_progress()
            if progress:
                progress.deleting(f"[dim]skip[/dim] {child.name}", category=category)
                progress.advance()
            continue

        ok, msg = force_remove_tree(child, category=category)
        if ok:
            removed += 1
        else:
            skipped += 1
            if msg:
                errors.append(f"{child.name}: {msg}")

    success = removed > 0 or (len(children) == 0)
    message = "; ".join(errors[:2])
    if skipped:
        extra = f"skipped {skipped} locked or protected item(s)"
        message = f"{message}; {extra}" if message else extra

    return success, message, removed, skipped


def _unlink_single(path: Path) -> tuple[bool, str]:
    try:
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()
        return True, ""
    except OSError as exc:
        return False, str(exc)


def delete_targets(
    targets: list[Path],
    *,
    category: str = "",
) -> tuple[bool, str, int]:
    """Delete enumerated paths one-by-one, reporting each to progress."""
    progress = get_deletion_progress()
    if progress:
        progress.set_category(category)

    errors: list[str] = []
    reclaimed = 0
    removed = 0
    skipped = 0

    for path in targets:
        if progress:
            progress.deleting(path, category=category)

        if path.exists():
            if path.is_dir() and not path.is_symlink():
                ok, msg = force_remove_tree(path, category=category)
                if ok:
                    removed += 1
                else:
                    skipped += 1
                    if msg:
                        errors.append(f"{path}: {msg}")
                continue

            try:
                size = path.stat().st_size if path.is_file() else 0
            except OSError:
                size = 0
            ok, msg = _unlink_single(path)
            if ok:
                reclaimed += size
                removed += 1
            else:
                skipped += 1
                errors.append(f"{path}: {msg}")

        if progress:
            progress.advance()

    success = removed > 0 or not targets
    message = "; ".join(errors[:2])
    if skipped:
        extra = f"skipped {skipped} locked item(s)"
        message = f"{message}; {extra}" if message else extra

    return success, message, reclaimed


def remove_path(path: Path, *, category: str = "") -> tuple[bool, str]:
    if not path.exists():
        return True, ""
    return force_remove_tree(path, category=category)


def clear_directory(path: Path, *, category: str = "") -> tuple[bool, str]:
    if not path.exists():
        return True, ""
    if not path.is_dir():
        ok, _ = force_remove_tree(path, category=category)
        return ok, "" if ok else "delete failed"

    ok, msg, _, _ = clear_directory_children(path, category=category)
    return ok, msg


def run_command(
    cmd: list[str],
    *,
    sudo: bool = False,
    timeout: int = 600,
    category: str = "",
    label: str | None = None,
) -> tuple[bool, str]:
    progress = get_deletion_progress()
    if progress:
        progress.deleting(label or " ".join(cmd), category=category or progress.category)

    if sudo:
        ready, msg = ensure_sudo()
        if not ready:
            if progress:
                progress.advance()
            return False, msg

    full_cmd = ["sudo", *cmd] if sudo else cmd
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if progress:
            progress.advance()
        if result.returncode == 0:
            return True, (result.stdout or "").strip()
        output = (result.stderr or result.stdout or "").strip()
        return False, output or f"exit code {result.returncode}"
    except subprocess.SubprocessError as exc:
        if progress:
            progress.advance()
        return False, str(exc)


def run_sudo_find_delete(
    *,
    root: Path,
    name_patterns: list[str],
    category: str = "",
    label: str = "files",
) -> tuple[bool, str]:
    """Delete many files under root with a single sudo find command."""
    progress = get_deletion_progress()
    if progress:
        progress.deleting(label, category=category)

    ready, msg = ensure_sudo()
    if not ready:
        if progress:
            progress.advance()
        return False, msg

    args = ["sudo", "find", str(root), "-type", "f", "("]
    for index, pattern in enumerate(name_patterns):
        if index > 0:
            args.append("-o")
        args.extend(["-name", pattern])
    args.extend([")", "-delete"])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if progress:
            progress.advance()
        if result.returncode == 0:
            return True, ""
        output = (result.stderr or result.stdout or "").strip()
        return False, output or f"exit code {result.returncode}"
    except subprocess.SubprocessError as exc:
        if progress:
            progress.advance()
        return False, str(exc)


def command_exists(name: str) -> bool:
    try:
        result = subprocess.run(
            ["which", name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def docker_daemon_running() -> bool:
    if not command_exists("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            return False
        output = (result.stderr or result.stdout or "").lower()
        return "cannot connect" not in output and "is the docker daemon running" not in output
    except subprocess.SubprocessError:
        return False
