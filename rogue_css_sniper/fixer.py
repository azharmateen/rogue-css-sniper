"""Auto-fix: replace hardcoded values with token references, interactive mode, generate diff."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rogue_css_sniper.matcher import TokenMatch


@dataclass
class Fix:
    """A single fix to apply."""
    file: str
    line: int
    original: str
    replacement: str
    token_name: str
    confidence: str
    applied: bool = False


@dataclass
class FixResult:
    """Summary of fixes applied."""
    total_violations: int = 0
    fixes_suggested: int = 0
    fixes_applied: int = 0
    fixes_skipped: int = 0
    files_modified: list[str] = field(default_factory=list)


class Fixer:
    """Apply token replacements to source files."""

    def __init__(
        self,
        css_var_format: str = "var(--{token})",
        min_confidence: str = "close",
        interactive: bool = False,
    ) -> None:
        self.css_var_format = css_var_format
        self.min_confidence = min_confidence
        self.interactive = interactive
        self.fixes: list[Fix] = []

    def plan_fixes(self, matches: list[TokenMatch]) -> list[Fix]:
        """Create a fix plan from matched tokens."""
        self.fixes = []
        confidence_order = {"exact": 0, "close": 1, "approximate": 2, "far": 3}
        min_level = confidence_order.get(self.min_confidence, 1)

        for m in matches:
            level = confidence_order.get(m.confidence, 3)
            if level > min_level:
                continue
            if not m.suggestion:
                continue

            # Determine replacement format
            replacement = self._format_replacement(m)

            self.fixes.append(Fix(
                file=m.violation.file,
                line=m.violation.line,
                original=m.violation.original_value,
                replacement=replacement,
                token_name=m.token_name,
                confidence=m.confidence,
            ))

        return self.fixes

    def _format_replacement(self, match: TokenMatch) -> str:
        """Format the replacement value based on value type."""
        if match.violation.value_type == "color":
            return self.css_var_format.format(token=match.token_name)
        elif match.violation.value_type == "spacing":
            # For CSS: use var(), for Tailwind classes: use class name
            return self.css_var_format.format(token=match.token_name)
        elif match.violation.value_type == "font-size":
            return self.css_var_format.format(token=match.token_name)
        elif match.violation.value_type == "z-index":
            return self.css_var_format.format(token=match.token_name)
        return match.suggestion

    def apply_fixes(self, dry_run: bool = False) -> FixResult:
        """Apply planned fixes to files.

        Args:
            dry_run: If True, only show what would change.

        Returns:
            FixResult with summary.
        """
        result = FixResult(
            total_violations=len(self.fixes),
            fixes_suggested=len(self.fixes),
        )

        # Group fixes by file
        fixes_by_file: dict[str, list[Fix]] = {}
        for fix in self.fixes:
            if fix.file not in fixes_by_file:
                fixes_by_file[fix.file] = []
            fixes_by_file[fix.file].append(fix)

        for file_path, file_fixes in fixes_by_file.items():
            path = Path(file_path)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            modified = False

            # Sort fixes by line number (descending) to apply from bottom up
            file_fixes.sort(key=lambda f: f.line, reverse=True)

            for fix in file_fixes:
                if fix.line > len(lines):
                    continue

                line_idx = fix.line - 1
                old_line = lines[line_idx]

                if self.interactive and not dry_run:
                    if not self._prompt_fix(fix, old_line):
                        fix.applied = False
                        result.fixes_skipped += 1
                        continue

                # Apply the replacement
                new_line = old_line.replace(fix.original, fix.replacement, 1)
                if new_line != old_line:
                    lines[line_idx] = new_line
                    fix.applied = True
                    modified = True
                    result.fixes_applied += 1
                else:
                    result.fixes_skipped += 1

            if modified and not dry_run:
                path.write_text("".join(lines), encoding="utf-8")
                result.files_modified.append(file_path)

        return result

    def generate_diff(self) -> str:
        """Generate a unified diff of all planned fixes."""
        lines = []
        fixes_by_file: dict[str, list[Fix]] = {}
        for fix in self.fixes:
            if fix.file not in fixes_by_file:
                fixes_by_file[fix.file] = []
            fixes_by_file[fix.file].append(fix)

        for file_path, file_fixes in sorted(fixes_by_file.items()):
            path = Path(file_path)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")
            file_lines = content.splitlines()

            lines.append(f"--- a/{path.name}")
            lines.append(f"+++ b/{path.name}")

            for fix in sorted(file_fixes, key=lambda f: f.line):
                if fix.line > len(file_lines):
                    continue
                old_line = file_lines[fix.line - 1]
                new_line = old_line.replace(fix.original, fix.replacement, 1)

                lines.append(f"@@ -{fix.line},1 +{fix.line},1 @@")
                lines.append(f"-{old_line}")
                lines.append(f"+{new_line}")

        return "\n".join(lines)

    @staticmethod
    def _prompt_fix(fix: Fix, old_line: str) -> bool:
        """Prompt user to accept or reject a fix."""
        new_line = old_line.replace(fix.original, fix.replacement, 1)
        print(f"\n--- {fix.file}:{fix.line} ({fix.confidence}) ---")
        print(f"  - {old_line.strip()}")
        print(f"  + {new_line.strip()}")
        print(f"  Token: {fix.token_name}")
        while True:
            answer = input("  Apply? [y/n/q] ").strip().lower()
            if answer == "y":
                return True
            elif answer in ("n", ""):
                return False
            elif answer == "q":
                raise KeyboardInterrupt("User quit interactive mode")
