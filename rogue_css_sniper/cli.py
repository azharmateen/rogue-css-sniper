"""Click CLI for rogue-css-sniper: scan, fix, report."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from rogue_css_sniper import __version__
from rogue_css_sniper.fixer import Fixer
from rogue_css_sniper.matcher import Matcher
from rogue_css_sniper.reporter import Reporter
from rogue_css_sniper.scanner import Scanner
from rogue_css_sniper.tokens import TokenDatabase

console = Console()


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """rogue-css-sniper: Hunt down hardcoded CSS values and snap them to design tokens."""


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--tokens", "-t", "tokens_path", type=click.Path(exists=True),
              help="Custom tokens file (JSON/YAML). Default: Tailwind v3.")
@click.option("--no-colors", is_flag=True, help="Skip color scanning")
@click.option("--no-spacing", is_flag=True, help="Skip spacing scanning")
@click.option("--no-fonts", is_flag=True, help="Skip font-size scanning")
@click.option("--no-z-index", is_flag=True, help="Skip z-index scanning")
@click.option("--json-out", "-j", type=click.Path(), help="Save JSON report")
@click.option("--md-out", type=click.Path(), help="Save markdown report")
@click.option("--ignore", "-i", multiple=True, help="Regex patterns to ignore (file paths)")
def scan(
    path: str,
    tokens_path: str | None,
    no_colors: bool,
    no_spacing: bool,
    no_fonts: bool,
    no_z_index: bool,
    json_out: str | None,
    md_out: str | None,
    ignore: tuple,
) -> None:
    """Scan files for hardcoded CSS values."""
    console.print(f"\n[bold]Scanning:[/bold] {path}")

    # Load tokens
    tokens = TokenDatabase.from_tailwind()
    if tokens_path:
        custom = TokenDatabase.from_file(tokens_path)
        tokens.merge(custom)
        console.print(f"  Custom tokens loaded from: {tokens_path}")

    # Scan
    scanner = Scanner(
        scan_colors=not no_colors,
        scan_spacing=not no_spacing,
        scan_font_sizes=not no_fonts,
        scan_z_index=not no_z_index,
        ignore_patterns=list(ignore),
    )

    with console.status("Scanning files..."):
        violations = scanner.scan_path(path)

    if not violations:
        console.print("\n[green]No violations found. Your CSS is clean![/green]")
        return

    # Match to tokens
    matcher = Matcher(tokens)
    matches = matcher.match_all(violations)

    # Report
    reporter = Reporter(violations=violations, matches=matches)
    reporter.print_terminal(console)

    if json_out:
        reporter.to_json(json_out)
        console.print(f"\n[green]JSON report saved:[/green] {json_out}")
    if md_out:
        reporter.to_markdown(md_out)
        console.print(f"[green]Markdown report saved:[/green] {md_out}")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--tokens", "-t", "tokens_path", type=click.Path(exists=True),
              help="Custom tokens file")
@click.option("--interactive", "-i", is_flag=True, help="Prompt for each fix (y/n)")
@click.option("--dry-run", is_flag=True, help="Show diff without applying changes")
@click.option("--min-confidence", type=click.Choice(["exact", "close", "approximate"]),
              default="close", help="Minimum match confidence to apply")
@click.option("--css-var-format", default="var(--{token})",
              help="Format string for CSS variable replacement")
def fix(
    path: str,
    tokens_path: str | None,
    interactive: bool,
    dry_run: bool,
    min_confidence: str,
    css_var_format: str,
) -> None:
    """Auto-fix hardcoded values with design tokens."""
    console.print(f"\n[bold]{'Dry run' if dry_run else 'Fixing'}:[/bold] {path}")

    # Load tokens
    tokens = TokenDatabase.from_tailwind()
    if tokens_path:
        custom = TokenDatabase.from_file(tokens_path)
        tokens.merge(custom)

    # Scan
    scanner = Scanner()
    violations = scanner.scan_path(path)

    if not violations:
        console.print("[green]No violations found.[/green]")
        return

    # Match
    matcher = Matcher(tokens)
    matches = matcher.match_all(violations)

    # Plan and apply fixes
    fixer = Fixer(
        css_var_format=css_var_format,
        min_confidence=min_confidence,
        interactive=interactive,
    )
    fixes = fixer.plan_fixes(matches)

    if not fixes:
        console.print("[yellow]No auto-fixable violations found at the selected confidence level.[/yellow]")
        return

    console.print(f"  Found {len(fixes)} fixable violations")

    if dry_run:
        diff = fixer.generate_diff()
        console.print("\n[bold]Diff preview:[/bold]\n")
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/cyan]")
            else:
                console.print(line)
        return

    try:
        result = fixer.apply_fixes(dry_run=False)
    except KeyboardInterrupt:
        console.print("\n[yellow]Aborted by user.[/yellow]")
        return

    console.print(f"\n[bold]Fix Results:[/bold]")
    console.print(f"  Applied: [green]{result.fixes_applied}[/green]")
    console.print(f"  Skipped: {result.fixes_skipped}")
    console.print(f"  Files modified: {len(result.files_modified)}")
    for f in result.files_modified:
        console.print(f"    [dim]{f}[/dim]")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--tokens", "-t", "tokens_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "markdown"]),
              default="terminal")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
def report(path: str, tokens_path: str | None, fmt: str, output: str | None) -> None:
    """Generate a detailed report of CSS violations."""
    tokens = TokenDatabase.from_tailwind()
    if tokens_path:
        tokens.merge(TokenDatabase.from_file(tokens_path))

    scanner = Scanner()
    violations = scanner.scan_path(path)
    matcher = Matcher(tokens)
    matches = matcher.match_all(violations)
    reporter = Reporter(violations=violations, matches=matches)

    if fmt == "terminal":
        reporter.print_terminal(console)
    elif fmt == "json":
        text = reporter.to_json(output)
        if not output:
            console.print(text)
    elif fmt == "markdown":
        text = reporter.to_markdown(output)
        if not output:
            console.print(text)

    if output and fmt != "terminal":
        console.print(f"[green]Report saved:[/green] {output}")


if __name__ == "__main__":
    cli()
