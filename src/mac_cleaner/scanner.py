"""Disk usage scanning utilities."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def path_size(path: Path) -> int:
    """Return total byte size for a file or directory."""
    if not path.exists():
        return 0

    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    try:
        result = subprocess.run(
            ["du", "-sk", str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.split()[0]) * 1024
    except (subprocess.SubprocessError, ValueError, IndexError):
        pass

    return _walk_size(path)


def paths_size(paths: list[Path]) -> int:
    return sum(path_size(p) for p in paths)


def _walk_size(path: Path) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def existing_paths(*candidates: Path | str) -> list[Path]:
    found: list[Path] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists():
            found.append(path)
    return found


def enumerate_deletion_items(
    root: Path,
    *,
    contents_only: bool = False,
) -> list[Path]:
    """Return paths to delete, deepest entries first."""
    if not root.exists():
        return []

    try:
        if root.is_file() or root.is_symlink():
            return [root]

        if not root.is_dir():
            return []

        if contents_only:
            items: list[Path] = []
            for child in root.iterdir():
                items.extend(enumerate_deletion_items(child, contents_only=False))
            return items

        items: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
            for name in filenames:
                items.append(Path(dirpath) / name)
            for name in dirnames:
                items.append(Path(dirpath) / name)
        items.append(root)
        return items
    except OSError:
        return []


def targets_from_paths(
    paths: list[Path],
    *,
    contents_only: bool = False,
) -> list[Path]:
    """Merge deletion targets from multiple roots without duplicates."""
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        for item in enumerate_deletion_items(path, contents_only=contents_only):
            key = str(item)
            if key not in seen:
                seen.add(key)
                ordered.append(item)
    return ordered

