"""Reports: terminal table, JSON, markdown, summary stats."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from rogue_css_sniper.fixer import Fix, FixResult
from rogue_css_sniper.matcher import TokenMatch
from rogue_css_sniper.scanner import Violation


class Reporter:
    """Generate reports from scan results."""

    def __init__(
        self,
        violations: list[Violation] | None = None,
        matches: list[TokenMatch] | None = None,
        fix_result: FixResult | None = None,
    ) -> None:
        self.violations = violations or []
        self.matches = matches or []
        self.fix_result = fix_result

    # ------------------------------------------------------------------
    # Terminal (Rich)
    # ------------------------------------------------------------------
    def print_terminal(self, console: Console | None = None, show_suggestions: bool = True) -> None:
        """Print violations table to terminal."""
        console = console or Console()

        if not self.violations:
            console.print("[green]No violations found. Your CSS is clean![/green]")
            return

        # Summary stats
        stats = self._compute_stats()
        console.print(f"\n[bold]Scan Results[/bold]")
        console.print(f"  Files scanned:     {stats['files_scanned']}")
        console.print(f"  Total violations:  [red]{stats['total_violations']}[/red]")
        console.print(f"  Colors:            {stats['by_type'].get('color', 0)}")
        console.print(f"  Spacing:           {stats['by_type'].get('spacing', 0)}")
        console.print(f"  Font sizes:        {stats['by_type'].get('font-size', 0)}")
        console.print(f"  Z-index:           {stats['by_type'].get('z-index', 0)}")
        if self.matches:
            fixable = sum(1 for m in self.matches if m.confidence in ("exact", "close"))
            console.print(f"  Auto-fixable:      [green]{fixable}[/green]")
        console.print()

        # Violations table
        table = Table(show_header=True, title="Violations")
        table.add_column("#", style="dim", width=4)
        table.add_column("File", max_width=30)
        table.add_column("Line", width=5)
        table.add_column("Type", width=10)
        table.add_column("Value", width=20)
        table.add_column("Property", width=14)
        if show_suggestions and self.matches:
            table.add_column("Suggestion", width=25)
            table.add_column("Conf.", width=8)

        match_map = {id(m.violation): m for m in self.matches}

        for i, v in enumerate(self.violations, 1):
            type_color = {
                "color": "magenta",
                "spacing": "cyan",
                "font-size": "yellow",
                "z-index": "blue",
            }.get(v.value_type, "white")

            row = [
                str(i),
                _shorten_path(v.file),
                str(v.line),
                f"[{type_color}]{v.value_type}[/{type_color}]",
                v.original_value,
                v.property_name,
            ]

            if show_suggestions and self.matches:
                match = match_map.get(id(v))
                if match:
                    conf_color = {"exact": "green", "close": "green",
                                  "approximate": "yellow", "far": "red"}.get(match.confidence, "white")
                    row.append(match.suggestion or "-")
                    row.append(f"[{conf_color}]{match.confidence}[/{conf_color}]")
                else:
                    row.extend(["-", "-"])

            table.add_row(*row)

            # Show first 50 only
            if i >= 50 and len(self.violations) > 50:
                console.print(table)
                console.print(f"[dim]... and {len(self.violations) - 50} more violations[/dim]")
                return

        console.print(table)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------
    def to_json(self, path: str | Path | None = None) -> str:
        """Generate JSON report."""
        data = {
            "summary": self._compute_stats(),
            "violations": [v.to_dict() for v in self.violations],
        }
        if self.matches:
            data["matches"] = [m.to_dict() for m in self.matches]
        if self.fix_result:
            data["fix_result"] = {
                "total_violations": self.fix_result.total_violations,
                "fixes_applied": self.fix_result.fixes_applied,
                "fixes_skipped": self.fix_result.fixes_skipped,
                "files_modified": self.fix_result.files_modified,
            }

        text = json.dumps(data, indent=2, ensure_ascii=False)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text)
        return text

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------
    def to_markdown(self, path: str | Path | None = None) -> str:
        """Generate markdown report."""
        stats = self._compute_stats()
        lines = [
            "# CSS Token Violation Report",
            "",
            f"**Total violations:** {stats['total_violations']}",
            f"**Files scanned:** {stats['files_scanned']}",
            "",
            "## Summary by Type",
            "",
            "| Type | Count |",
            "|------|-------|",
        ]
        for vtype, count in sorted(stats["by_type"].items()):
            lines.append(f"| {vtype} | {count} |")

        lines.extend(["", "## Top Files", "", "| File | Violations |", "|------|------------|"])
        for filepath, count in stats["by_file"].most_common(10):
            lines.append(f"| {_shorten_path(filepath)} | {count} |")

        lines.extend(["", "## Violations", "", "| # | File | Line | Type | Value | Suggestion |",
                       "|---|------|------|------|-------|------------|"])

        match_map = {}
        for m in self.matches:
            key = (m.violation.file, m.violation.line, m.violation.original_value)
            match_map[key] = m

        for i, v in enumerate(self.violations[:100], 1):
            key = (v.file, v.line, v.original_value)
            suggestion = match_map[key].suggestion if key in match_map else "-"
            lines.append(
                f"| {i} | {_shorten_path(v.file)} | {v.line} | {v.value_type} "
                f"| `{v.original_value}` | `{suggestion}` |"
            )

        if len(self.violations) > 100:
            lines.append(f"\n*... and {len(self.violations) - 100} more*")

        lines.append("\n---\n*Generated by [rogue-css-sniper](https://github.com/rogue-css-sniper/rogue-css-sniper)*")

        text = "\n".join(lines)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text)
        return text

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _compute_stats(self) -> dict[str, Any]:
        by_type: Counter = Counter()
        by_file: Counter = Counter()
        files: set[str] = set()

        for v in self.violations:
            by_type[v.value_type] += 1
            by_file[v.file] += 1
            files.add(v.file)

        return {
            "total_violations": len(self.violations),
            "files_scanned": len(files),
            "by_type": dict(by_type),
            "by_file": by_file,
        }


def _shorten_path(path: str, max_len: int = 30) -> str:
    """Shorten a file path for display."""
    if len(path) <= max_len:
        return path
    parts = Path(path).parts
    if len(parts) <= 2:
        return path
    return f".../{'/'.join(parts[-2:])}"
