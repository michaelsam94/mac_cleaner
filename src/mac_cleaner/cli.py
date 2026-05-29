"""Click CLI entrypoint."""

from __future__ import annotations

import sys

import click

from mac_cleaner.cleaners.base import CleanResult, CleanStatus, format_bytes
from mac_cleaner.cleaners.registry import filter_cleaners, list_categories
from mac_cleaner.executor import ensure_sudo
from mac_cleaner.reporter import console, print_banner, print_results, run_cleaners_with_progress
from mac_cleaner.scheduler import (
    format_sudoers_instructions,
    install_schedule,
    schedule_status,
    sudo_categories,
    uninstall_schedule,
)


def _run_scan(cleaners) -> list[CleanResult]:
    return run_cleaners_with_progress(
        cleaners,
        operation="Scanning",
        action=lambda cleaner: cleaner.scan(),
        file_level=False,
    )


def _run_clean(cleaners, *, dry_run: bool) -> list[CleanResult]:
    operation = "Previewing" if dry_run else "Cleaning"
    return run_cleaners_with_progress(
        cleaners,
        operation=operation,
        action=lambda cleaner: cleaner.clean(dry_run=dry_run),
        track_reclaimed=not dry_run,
        file_level=True,
        dry_run=dry_run,
    )


def _confirm_sudo(cleaners, *, assume_yes: bool) -> bool:
    sudo_cats = [c.category for c in cleaners if c.requires_sudo]
    if not sudo_cats:
        return True
    console.print(
        f"\n[yellow]These categories require sudo:[/yellow] {', '.join(sudo_cats)}"
    )
    if assume_yes:
        return True
    return click.confirm("Continue with sudo operations?", default=False)


def _confirm_execute(*, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return click.confirm(
        "\n[red bold]This will permanently delete files.[/red bold] Continue?",
        default=False,
    )


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Aggressive macOS cache cleaner."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(scan)


@cli.command()
@click.option(
    "--category",
    "-c",
    multiple=True,
    help=f"Limit to categories. Available: {', '.join(list_categories())}",
)
def scan(category: tuple[str, ...]) -> None:
    """Scan and show reclaimable space per category."""
    print_banner()
    cleaners = filter_cleaners(category or None)
    if category and not cleaners:
        console.print(f"[red]No matching categories. Available: {', '.join(list_categories())}[/red]")
        sys.exit(1)
    results = _run_scan(cleaners)
    print_results(results, title="Reclaimable Space")
    console.print("\nRun [bold]mac-cleaner clean[/bold] to preview deletion.")
    console.print("Run [bold]mac-cleaner clean --execute[/bold] to delete.")


@cli.command()
@click.option("--execute", is_flag=True, help="Actually delete files (default is dry-run).")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompts.")
@click.option(
    "--category",
    "-c",
    multiple=True,
    help=f"Limit to categories. Available: {', '.join(list_categories())}",
)
def clean(execute: bool, yes: bool, category: tuple[str, ...]) -> None:
    """Clean caches. Dry-run unless --execute is passed."""
    print_banner()
    cleaners = filter_cleaners(category or None)
    if category and not cleaners:
        console.print(f"[red]No matching categories. Available: {', '.join(list_categories())}[/red]")
        sys.exit(1)

    dry_run = not execute
    if execute:
        if not _confirm_execute(assume_yes=yes):
            console.print("[yellow]Aborted.[/yellow]")
            sys.exit(0)
        if not _confirm_sudo(cleaners, assume_yes=yes):
            console.print("[yellow]Aborted.[/yellow]")
            sys.exit(0)
        console.print(
            "\n[yellow]Enter your Mac password once when prompted (for system cleanup).[/yellow]"
        )
        ok, msg = ensure_sudo()
        if not ok:
            console.print(f"[red]{msg}[/red]")
            sys.exit(1)

    console.print(f"[dim]Processing {len(cleaners)} categories...[/dim]\n")
    results = _run_clean(cleaners, dry_run=dry_run)
    title = "Dry Run Preview" if dry_run else "Cleanup Results"
    print_results(results, title=title)

    if dry_run:
        console.print("\n[dim]No files were deleted. Use --execute to apply.[/dim]")
    else:
        cleaned = sum(r.size_bytes for r in results if r.status == CleanStatus.CLEANED)
        console.print(f"\n[green bold]Reclaimed approximately {format_bytes(cleaned)}[/green bold]")

    if any(r.status == CleanStatus.FAILED for r in results):
        cleaned_any = any(r.status == CleanStatus.CLEANED for r in results)
        if not cleaned_any:
            sys.exit(1)


@cli.command("categories")
def categories_cmd() -> None:
    """List all cleanup categories."""
    for name in list_categories():
        console.print(f"  • {name}")


@cli.group()
def schedule() -> None:
    """Install periodic unattended cleanup via macOS launchd."""


@schedule.command("install")
@click.option(
    "--days",
    required=True,
    type=click.IntRange(1, None),
    help="Run cleanup every N days (no manual runs needed).",
)
@click.option(
    "--category",
    "-c",
    multiple=True,
    help=f"Limit to categories. Available: {', '.join(list_categories())}",
)
@click.option(
    "--include-sudo",
    is_flag=True,
    help="All categories; macOS admin password dialog on install and each run.",
)
@click.option(
    "--unattended-full",
    is_flag=True,
    help="All categories with no prompts; requires sudoers setup (printed below).",
)
def schedule_install(
    days: int,
    category: tuple[str, ...],
    include_sudo: bool,
    unattended_full: bool,
) -> None:
    """Register a LaunchAgent that runs mac-cleaner clean --execute -y on an interval."""
    if include_sudo and unattended_full:
        console.print("[red]Use either --include-sudo or --unattended-full, not both.[/red]")
        sys.exit(1)

    if not include_sudo and not unattended_full:
        console.print(
            "[dim]Scheduling user-level categories only "
            f"(skipping sudo: {', '.join(sudo_categories())}).[/dim]"
        )
        console.print(
            "[dim]Use --include-sudo (password each run) or "
            "--unattended-full (sudoers, no prompts).[/dim]\n"
        )

    ok, msg, plist_path = install_schedule(
        days,
        category or None,
        admin_prompt=include_sudo,
        unattended_full=unattended_full,
    )
    if not ok:
        console.print(f"[red]{msg}[/red]")
        sys.exit(1)

    console.print(f"[green]Scheduled cleanup every {days} day(s).[/green]")
    console.print(f"LaunchAgent: [bold]{plist_path}[/bold]")
    if unattended_full:
        console.print("Runs: [bold]all categories[/bold], direct launchd (no password dialogs).")
        console.print(
            "\n[yellow bold]Required one-time setup — passwordless sudo for cleanup commands:[/yellow bold]"
        )
        console.print(f"[dim]{format_sudoers_instructions()}[/dim]")
        console.print(
            "[dim]After saving, verify with: sudo -n rm -f /dev/null  (no password prompt)[/dim]"
        )
    elif include_sudo:
        console.print(
            "Runs: [bold]all categories[/bold] — macOS will ask for your admin password "
            "now and on each scheduled run."
        )
    else:
        console.print(
            "Runs: [bold]mac-cleaner clean --execute -y[/bold]"
            + (" -c …" if category else " (non-sudo categories)")
        )
    console.print("\n[dim]Logs: ~/Library/Logs/mac-cleaner-scheduled.log[/dim]")


@schedule.command("uninstall")
def schedule_uninstall() -> None:
    """Remove the scheduled LaunchAgent."""
    uninstall_schedule()
    console.print("[green]Removed scheduled cleanup LaunchAgent.[/green]")


@schedule.command("status")
def schedule_status_cmd() -> None:
    """Show whether periodic cleanup is installed and loaded."""
    info = schedule_status()
    if not info["installed"]:
        console.print("[yellow]No schedule installed.[/yellow]")
        console.print("Run [bold]mac-cleaner schedule install --days N[/bold] to enable.")
        return

    loaded = "loaded" if info["loaded"] else "not loaded"
    days = info["days"]
    interval = f"every {days} day(s)" if days else "interval unknown"
    console.print(f"[green]Schedule installed[/green] ({loaded}, {interval})")
    console.print(f"Plist: [bold]{info['plist_path']}[/bold]")
    if info.get("unattended_full"):
        console.print("Mode: [bold]unattended full[/bold] (all categories, sudoers required)")
    elif info.get("uses_admin_prompt"):
        console.print("Mode: [bold]admin password prompt[/bold] each run (all categories)")
        wrapper = info.get("wrapper_script")
        if wrapper:
            console.print(f"Wrapper: [dim]{wrapper}[/dim]")
    argv = info["program_arguments"]
    if argv:
        console.print(f"Launch: [dim]{' '.join(str(a) for a in argv)}[/dim]")
    console.print(f"Logs: [dim]{info['stdout_log']}[/dim]")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
