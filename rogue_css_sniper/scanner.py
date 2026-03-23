"""Scan CSS/SCSS/TSX/Vue files for hardcoded values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Patterns for hardcoded values
# ---------------------------------------------------------------------------

# Colors
HEX_COLOR_RE = re.compile(
    r'(?<![a-zA-Z0-9_-])#([0-9a-fA-F]{3,8})\b'
)
RGB_RE = re.compile(
    r'rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d.]+)?\s*\)'
)
HSL_RE = re.compile(
    r'hsla?\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?(?:\s*,\s*[\d.]+)?\s*\)'
)

# Pixel values (not 0px)
PX_RE = re.compile(r'(?<![a-zA-Z0-9_-])(\d+(?:\.\d+)?)px\b')

# rem/em values
REM_RE = re.compile(r'(?<![a-zA-Z0-9_-])(\d+(?:\.\d+)?)(?:rem|em)\b')

# z-index values
Z_INDEX_RE = re.compile(r'z-index\s*:\s*(\d+)')

# Font sizes
FONT_SIZE_RE = re.compile(r'font-size\s*:\s*(\d+(?:\.\d+)?)(px|rem|em)')

# File extensions to scan
SCANNABLE_EXTENSIONS = {
    ".css", ".scss", ".sass", ".less",
    ".tsx", ".jsx", ".vue", ".svelte",
    ".html", ".htm",
    ".styled.ts", ".styled.js",
}

# Properties to skip (variables, custom properties, comments, etc.)
SKIP_PATTERNS = [
    re.compile(r'^\s*//'),        # Line comments
    re.compile(r'^\s*/\*'),       # Block comment start
    re.compile(r'^\s*\*'),        # Block comment continuation
    re.compile(r'--[\w-]+\s*:'),  # CSS custom property definitions
    re.compile(r'var\(--'),       # CSS variable usage (already tokenized)
    re.compile(r'\$[\w-]+\s*:'),  # SCSS variable definitions
]


@dataclass
class Violation:
    """A hardcoded value found in source code."""
    file: str
    line: int
    column: int
    original_value: str
    value_type: str  # "color", "spacing", "font-size", "z-index"
    property_name: str  # CSS property (e.g., "color", "margin", "font-size")
    context: str  # The full line of code

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "original_value": self.original_value,
            "value_type": self.value_type,
            "property_name": self.property_name,
            "context": self.context.strip(),
        }


class Scanner:
    """Scan source files for hardcoded CSS values."""

    def __init__(
        self,
        scan_colors: bool = True,
        scan_spacing: bool = True,
        scan_font_sizes: bool = True,
        scan_z_index: bool = True,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        self.scan_colors = scan_colors
        self.scan_spacing = scan_spacing
        self.scan_font_sizes = scan_font_sizes
        self.scan_z_index = scan_z_index
        self.ignore_patterns = [re.compile(p) for p in (ignore_patterns or [])]
        self.violations: list[Violation] = []

    def scan_path(self, path: str | Path) -> list[Violation]:
        """Scan a file or directory for violations."""
        self.violations = []
        path = Path(path)

        if path.is_file():
            self._scan_file(path)
        elif path.is_dir():
            for ext in SCANNABLE_EXTENSIONS:
                for file_path in path.rglob(f"*{ext}"):
                    # Skip node_modules, dist, build
                    parts = file_path.parts
                    if any(p in parts for p in ("node_modules", "dist", "build", ".next", "__pycache__")):
                        continue
                    self._scan_file(file_path)
        else:
            raise FileNotFoundError(f"Path not found: {path}")

        return self.violations

    def _scan_file(self, file_path: Path) -> None:
        """Scan a single file."""
        # Check ignore patterns
        path_str = str(file_path)
        for pattern in self.ignore_patterns:
            if pattern.search(path_str):
                return

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return

        for line_num, line in enumerate(content.splitlines(), 1):
            if self._should_skip_line(line):
                continue

            if self.scan_colors:
                self._find_colors(file_path, line_num, line)
            if self.scan_spacing:
                self._find_spacing(file_path, line_num, line)
            if self.scan_font_sizes:
                self._find_font_sizes(file_path, line_num, line)
            if self.scan_z_index:
                self._find_z_index(file_path, line_num, line)

    def _should_skip_line(self, line: str) -> bool:
        """Check if line should be skipped."""
        for pattern in SKIP_PATTERNS:
            if pattern.search(line):
                return True
        return False

    def _find_colors(self, file_path: Path, line_num: int, line: str) -> None:
        """Find hardcoded color values."""
        # Hex colors
        for match in HEX_COLOR_RE.finditer(line):
            hex_val = match.group(0)
            # Skip very short hex that might be IDs or timestamps
            raw = match.group(1)
            if len(raw) not in (3, 4, 6, 8):
                continue
            prop = _guess_property(line, match.start())
            self.violations.append(Violation(
                file=str(file_path),
                line=line_num,
                column=match.start() + 1,
                original_value=hex_val,
                value_type="color",
                property_name=prop,
                context=line,
            ))

        # RGB colors
        for match in RGB_RE.finditer(line):
            prop = _guess_property(line, match.start())
            self.violations.append(Violation(
                file=str(file_path),
                line=line_num,
                column=match.start() + 1,
                original_value=match.group(0),
                value_type="color",
                property_name=prop,
                context=line,
            ))

        # HSL colors
        for match in HSL_RE.finditer(line):
            prop = _guess_property(line, match.start())
            self.violations.append(Violation(
                file=str(file_path),
                line=line_num,
                column=match.start() + 1,
                original_value=match.group(0),
                value_type="color",
                property_name=prop,
                context=line,
            ))

    def _find_spacing(self, file_path: Path, line_num: int, line: str) -> None:
        """Find hardcoded pixel values (spacing/sizing)."""
        for match in PX_RE.finditer(line):
            px_val = float(match.group(1))
            if px_val == 0:
                continue  # 0px is fine

            prop = _guess_property(line, match.start())
            # Skip font-size (handled separately)
            if "font-size" in prop:
                continue

            self.violations.append(Violation(
                file=str(file_path),
                line=line_num,
                column=match.start() + 1,
                original_value=f"{match.group(1)}px",
                value_type="spacing",
                property_name=prop,
                context=line,
            ))

    def _find_font_sizes(self, file_path: Path, line_num: int, line: str) -> None:
        """Find hardcoded font-size values."""
        for match in FONT_SIZE_RE.finditer(line):
            self.violations.append(Violation(
                file=str(file_path),
                line=line_num,
                column=match.start() + 1,
                original_value=f"{match.group(1)}{match.group(2)}",
                value_type="font-size",
                property_name="font-size",
                context=line,
            ))

    def _find_z_index(self, file_path: Path, line_num: int, line: str) -> None:
        """Find hardcoded z-index values."""
        for match in Z_INDEX_RE.finditer(line):
            z_val = int(match.group(1))
            # Only flag non-standard z-index values
            if z_val not in (0, 10, 20, 30, 40, 50):
                self.violations.append(Violation(
                    file=str(file_path),
                    line=line_num,
                    column=match.start() + 1,
                    original_value=str(z_val),
                    value_type="z-index",
                    property_name="z-index",
                    context=line,
                ))


def _guess_property(line: str, position: int) -> str:
    """Try to guess the CSS property name from context."""
    # Look backwards from position for property name
    before = line[:position].strip()
    # Match "property:" at the end
    prop_match = re.search(r'([\w-]+)\s*:\s*$', before)
    if prop_match:
        return prop_match.group(1)
    # Check for style= in JSX/HTML
    style_match = re.search(r'(\w+)\s*[:=]\s*["\']?$', before)
    if style_match:
        return style_match.group(1)
    return "unknown"
