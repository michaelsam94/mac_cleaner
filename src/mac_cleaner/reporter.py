"""Rich terminal reporting."""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, Cleaner, format_bytes
from mac_cleaner.progress import DeletionProgress, set_deletion_progress

console = Console()


def print_results(results: list[CleanResult], *, title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Sudo", justify="center")
    table.add_column("Status")

    total = 0
    for result in results:
        if result.size_bytes > 0 or result.status.value != "skipped":
            total += result.size_bytes
        sudo = "yes" if result.requires_sudo else "—"
        status_style = {
            "ready": "yellow",
            "dry-run": "yellow",
            "cleaned": "green",
            "failed": "red",
            "skipped": "dim",
        }.get(result.status.value, "white")
        table.add_row(
            result.category,
            result.description,
            result.size_human,
            sudo,
            f"[{status_style}]{result.status.value}[/{status_style}]",
        )

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {format_bytes(total)}")

    failed = [r for r in results if r.status.value == "failed"]
    if failed:
        console.print("\n[red bold]Failures:[/red bold]")
        for result in failed:
            detail = f" — {result.message}" if result.message else ""
            console.print(f"  • {result.category}{detail}")


def print_banner() -> None:
    console.print("[bold blue]mac-cleaner[/bold blue] — aggressive macOS disk recovery\n")


def _failed_result(cleaner: Cleaner, exc: OSError) -> CleanResult:
    return CleanResult(
        category=cleaner.category,
        description=cleaner.description,
        size_bytes=0,
        status=CleanStatus.FAILED,
        message=str(exc),
        requires_sudo=cleaner.requires_sudo,
    )


def _cleaner_item_count(cleaner: Cleaner) -> int:
    return len(cleaner.get_deletion_targets()) + len(cleaner.get_command_steps())


def _is_active(cleaner: Cleaner) -> bool:
    scan = cleaner.scan()
    if scan.status != CleanStatus.SKIPPED or scan.size_bytes > 0:
        return True
    return _cleaner_item_count(cleaner) > 0


def discover_active_cleaners(cleaners: list[Cleaner]) -> tuple[list[Cleaner], int]:
    """Find cleaners with work to do and count total files/commands."""
    active: list[Cleaner] = []
    total_items = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Discovering files to delete...", total=len(cleaners))
        for cleaner in cleaners:
            progress.update(task_id, description=f"Discovering [cyan]{cleaner.category}[/cyan]...")
            if _is_active(cleaner):
                active.append(cleaner)
                total_items += _cleaner_item_count(cleaner)
            progress.advance(task_id)

    return active, total_items


def _preview_targets(cleaner: Cleaner, progress: DeletionProgress) -> None:
    progress.set_category(cleaner.category)
    for path in cleaner.get_deletion_targets():
        progress.deleting(path, category=cleaner.category)
        progress.advance()
    for step in cleaner.get_command_steps():
        progress.deleting(f"[dim]would run[/dim] {step}", category=cleaner.category)
        progress.advance()


def run_cleaners_with_progress(
    cleaners: list[Cleaner],
    *,
    operation: str,
    action: Callable[[Cleaner], CleanResult],
    track_reclaimed: bool = False,
    file_level: bool = False,
    dry_run: bool = False,
) -> list[CleanResult]:
    """Run cleaners with category-level or file-level progress."""
    if not file_level:
        return _run_category_progress(
            cleaners,
            operation=operation,
            action=action,
            track_reclaimed=track_reclaimed,
        )

    active, total_items = discover_active_cleaners(cleaners)
    if not active:
        return [cleaner.scan() for cleaner in cleaners]

    label = "preview" if dry_run else "delete"
    console.print(
        f"[dim]Found {total_items:,} file(s)/step(s) to {label} "
        f"across {len(active)} categories[/dim]\n"
    )

    active_set = {id(c) for c in active}
    results: list[CleanResult] = []
    reclaimed_bytes = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=32),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        refresh_per_second=15,
    ) as progress:
        task_id = progress.add_task(
            operation,
            total=max(total_items, 1),
        )
        deletion_progress = DeletionProgress(progress, task_id)
        set_deletion_progress(deletion_progress)

        try:
            for cleaner in cleaners:
                if id(cleaner) not in active_set:
                    skipped = cleaner.scan()
                    if skipped.status == CleanStatus.SKIPPED:
                        results.append(skipped)
                    else:
                        results.append(
                            CleanResult(
                                category=cleaner.category,
                                description=cleaner.description,
                                size_bytes=0,
                                status=CleanStatus.SKIPPED,
                                paths=skipped.paths,
                                requires_sudo=cleaner.requires_sudo,
                            )
                        )
                    continue

                try:
                    if dry_run:
                        _preview_targets(cleaner, deletion_progress)
                        result = cleaner.clean(dry_run=True)
                    else:
                        deletion_progress.set_category(cleaner.category)
                        result = cleaner.clean(dry_run=False)
                except OSError as exc:
                    result = _failed_result(cleaner, exc)
                except Exception as exc:
                    result = CleanResult(
                        category=cleaner.category,
                        description=cleaner.description,
                        size_bytes=0,
                        status=CleanStatus.FAILED,
                        message=str(exc),
                        requires_sudo=cleaner.requires_sudo,
                    )

                results.append(result)
                if track_reclaimed and result.status == CleanStatus.CLEANED:
                    reclaimed_bytes += result.size_bytes

            progress.update(
                task_id,
                description=f"[bold green]{operation} complete[/bold green]",
                completed=max(total_items, 1),
            )
        finally:
            set_deletion_progress(None)

    if track_reclaimed and reclaimed_bytes > 0:
        console.print(f"[green]Reclaimed so far: {format_bytes(reclaimed_bytes)}[/green]")
    console.print()
    return results


def _run_category_progress(
    cleaners: list[Cleaner],
    *,
    operation: str,
    action: Callable[[Cleaner], CleanResult],
    track_reclaimed: bool,
) -> list[CleanResult]:
    results: list[CleanResult] = []
    total = len(cleaners)
    reclaimed_bytes = 0

    if total == 0:
        return results

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=36),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        MofNCompleteColumn(),
        TextColumn("{task.fields[last_status]}"),
        TimeElapsedColumn(),
        TextColumn("{task.fields[reclaimed]}"),
        console=console,
        refresh_per_second=12,
    ) as progress:
        task_id = progress.add_task(
            operation,
            total=total,
            last_status="",
            reclaimed="",
        )

        for cleaner in cleaners:
            progress.update(
                task_id,
                description=f"{operation} [cyan]{cleaner.category}[/cyan]",
                last_status="",
            )
            try:
                result = action(cleaner)
            except OSError as exc:
                result = _failed_result(cleaner, exc)

            results.append(result)

            if track_reclaimed and result.status == CleanStatus.CLEANED:
                reclaimed_bytes += result.size_bytes

            status_style = {
                CleanStatus.CLEANED: "green",
                CleanStatus.DRY_RUN: "yellow",
                CleanStatus.FAILED: "red",
                CleanStatus.SKIPPED: "dim",
                CleanStatus.READY: "yellow",
            }.get(result.status, "white")

            reclaimed_field = (
                f"[green]{format_bytes(reclaimed_bytes)} reclaimed[/green]"
                if track_reclaimed and reclaimed_bytes > 0
                else ""
            )

            progress.update(
                task_id,
                advance=1,
                last_status=f"[{status_style}]✓ {result.status.value}[/{status_style}]",
                reclaimed=reclaimed_field,
            )

        progress.update(
            task_id,
            description=f"[bold green]{operation} complete[/bold green]",
            last_status="[green]100%[/green]",
        )

    console.print()
    return results
