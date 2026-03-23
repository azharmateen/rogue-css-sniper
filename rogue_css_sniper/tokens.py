"""Token database: load design tokens from JSON/YAML, Tailwind config, Style Dictionary format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from rogue_css_sniper.tailwind_tokens import (
    COLORS,
    FONT_SIZES,
    FONT_SIZES_BY_PX,
    SPACING,
    SPACING_BY_PX,
    Z_INDEX,
)


class TokenDatabase:
    """Manage design tokens from various sources."""

    def __init__(self) -> None:
        self.colors: dict[str, str] = {}  # name -> hex
        self.spacing: dict[str, float] = {}  # name -> px value
        self.spacing_by_px: dict[float, str] = {}
        self.font_sizes: dict[str, float] = {}  # name -> px value
        self.font_sizes_by_px: dict[float, str] = {}
        self.z_index: dict[str, int] = {}
        self.raw_tokens: dict[str, Any] = {}

    @classmethod
    def from_tailwind(cls) -> "TokenDatabase":
        """Create a token database with Tailwind v3 defaults."""
        db = cls()
        db.colors = dict(COLORS)
        db.spacing = dict(SPACING)
        db.spacing_by_px = dict(SPACING_BY_PX)
        db.font_sizes = dict(FONT_SIZES)
        db.font_sizes_by_px = dict(FONT_SIZES_BY_PX)
        db.z_index = dict(Z_INDEX)
        return db

    @classmethod
    def from_file(cls, path: str | Path) -> "TokenDatabase":
        """Load tokens from a JSON or YAML file.

        Supports:
        - Style Dictionary format (nested with $value)
        - Flat token format (key: value pairs)
        - Tailwind config theme format
        """
        path = Path(path)
        with open(path) as f:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        db = cls()
        db.raw_tokens = data

        # Try to detect format and extract tokens
        if "color" in data or "colors" in data:
            db._extract_flat_or_nested(data.get("color") or data.get("colors", {}), "color")
        if "spacing" in data:
            db._extract_spacing(data["spacing"])
        if "fontSize" in data or "font-size" in data:
            db._extract_font_sizes(data.get("fontSize") or data.get("font-size", {}))
        if "zIndex" in data or "z-index" in data:
            db._extract_z_index(data.get("zIndex") or data.get("z-index", {}))

        # Style Dictionary format
        if any(isinstance(v, dict) and "$value" in v for v in data.values()):
            db._extract_style_dictionary(data)

        # Tailwind config format
        if "theme" in data:
            theme = data["theme"]
            if "extend" in theme:
                theme = {**theme, **theme["extend"]}
            if "colors" in theme:
                db._extract_flat_or_nested(theme["colors"], "color")
            if "spacing" in theme:
                db._extract_spacing(theme["spacing"])
            if "fontSize" in theme:
                db._extract_font_sizes(theme["fontSize"])

        return db

    def merge(self, other: "TokenDatabase") -> "TokenDatabase":
        """Merge another token database into this one (other takes precedence)."""
        self.colors.update(other.colors)
        self.spacing.update(other.spacing)
        self.spacing_by_px.update(other.spacing_by_px)
        self.font_sizes.update(other.font_sizes)
        self.font_sizes_by_px.update(other.font_sizes_by_px)
        self.z_index.update(other.z_index)
        return self

    def _extract_flat_or_nested(self, data: dict, prefix: str = "") -> None:
        """Extract color tokens from flat or nested dict."""
        for key, value in data.items():
            if isinstance(value, str):
                name = f"{prefix}-{key}" if prefix else key
                if value.startswith("#") or value.startswith("rgb") or value.startswith("hsl"):
                    self.colors[name] = value
            elif isinstance(value, dict):
                if "$value" in value:
                    name = f"{prefix}-{key}" if prefix else key
                    self.colors[name] = value["$value"]
                else:
                    # Nested (e.g., {red: {100: "#fee2e2", 200: "#fecaca"}})
                    for sub_key, sub_val in value.items():
                        name = f"{key}-{sub_key}"
                        if isinstance(sub_val, str):
                            self.colors[name] = sub_val
                        elif isinstance(sub_val, dict) and "$value" in sub_val:
                            self.colors[name] = sub_val["$value"]

    def _extract_spacing(self, data: dict) -> None:
        """Extract spacing tokens."""
        for key, value in data.items():
            if isinstance(value, (int, float)):
                self.spacing[key] = float(value)
                self.spacing_by_px[float(value)] = key
            elif isinstance(value, str):
                # Parse "16px" or "1rem"
                px = _parse_to_px(value)
                if px is not None:
                    self.spacing[key] = px
                    self.spacing_by_px[px] = key

    def _extract_font_sizes(self, data: dict) -> None:
        """Extract font size tokens."""
        for key, value in data.items():
            if isinstance(value, (int, float)):
                self.font_sizes[key] = float(value)
                self.font_sizes_by_px[float(value)] = key
            elif isinstance(value, str):
                px = _parse_to_px(value)
                if px is not None:
                    self.font_sizes[key] = px
                    self.font_sizes_by_px[px] = key
            elif isinstance(value, list) and value:
                # Tailwind format: ["1.5rem", { lineHeight: "2rem" }]
                px = _parse_to_px(str(value[0]))
                if px is not None:
                    self.font_sizes[key] = px
                    self.font_sizes_by_px[px] = key

    def _extract_z_index(self, data: dict) -> None:
        """Extract z-index tokens."""
        for key, value in data.items():
            if isinstance(value, int):
                self.z_index[key] = value
            elif isinstance(value, str) and value.isdigit():
                self.z_index[key] = int(value)

    def _extract_style_dictionary(self, data: dict, prefix: str = "") -> None:
        """Extract tokens from Style Dictionary format."""
        for key, value in data.items():
            current = f"{prefix}-{key}" if prefix else key
            if isinstance(value, dict):
                if "$value" in value:
                    token_type = value.get("$type", "")
                    val = value["$value"]
                    if token_type == "color" or (isinstance(val, str) and val.startswith("#")):
                        self.colors[current] = val
                    elif token_type == "dimension":
                        px = _parse_to_px(str(val))
                        if px is not None:
                            self.spacing[current] = px
                            self.spacing_by_px[px] = current
                else:
                    self._extract_style_dictionary(value, current)


def _parse_to_px(value: str) -> float | None:
    """Parse a CSS length value to pixels."""
    value = value.strip()
    if value.endswith("px"):
        try:
            return float(value[:-2])
        except ValueError:
            return None
    if value.endswith("rem"):
        try:
            return float(value[:-3]) * 16  # Assume 16px base
        except ValueError:
            return None
    if value.endswith("em"):
        try:
            return float(value[:-2]) * 16
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None
