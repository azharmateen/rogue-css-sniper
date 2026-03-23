"""Match hardcoded values to nearest design token using color distance and numeric proximity."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from rogue_css_sniper.scanner import Violation
from rogue_css_sniper.tokens import TokenDatabase


@dataclass
class TokenMatch:
    """A suggested token replacement for a violation."""
    violation: Violation
    token_name: str
    token_value: str
    distance: float  # 0 = exact match, higher = further
    confidence: str  # "exact", "close", "approximate", "far"
    suggestion: str  # e.g., "text-red-500" or "p-4"

    def to_dict(self) -> dict[str, Any]:
        d = self.violation.to_dict()
        d.update({
            "token_name": self.token_name,
            "token_value": self.token_value,
            "distance": round(self.distance, 2),
            "confidence": self.confidence,
            "suggestion": self.suggestion,
        })
        return d


class Matcher:
    """Match hardcoded CSS values to design system tokens."""

    def __init__(self, tokens: TokenDatabase) -> None:
        self.tokens = tokens

    def match_violation(self, violation: Violation) -> TokenMatch | None:
        """Find the best matching token for a violation."""
        if violation.value_type == "color":
            return self._match_color(violation)
        elif violation.value_type == "spacing":
            return self._match_spacing(violation)
        elif violation.value_type == "font-size":
            return self._match_font_size(violation)
        elif violation.value_type == "z-index":
            return self._match_z_index(violation)
        return None

    def match_all(self, violations: list[Violation]) -> list[TokenMatch]:
        """Match all violations to tokens."""
        matches = []
        for v in violations:
            m = self.match_violation(v)
            if m:
                matches.append(m)
        return matches

    # ------------------------------------------------------------------
    # Color matching (Delta-E in LAB space)
    # ------------------------------------------------------------------
    def _match_color(self, violation: Violation) -> TokenMatch | None:
        """Match a color value to the nearest color token."""
        target_rgb = _parse_color(violation.original_value)
        if not target_rgb:
            return None

        target_lab = _rgb_to_lab(*target_rgb)
        best_name = ""
        best_hex = ""
        best_dist = float("inf")

        for name, hex_val in self.tokens.colors.items():
            token_rgb = _parse_color(hex_val)
            if not token_rgb:
                continue
            token_lab = _rgb_to_lab(*token_rgb)
            dist = _delta_e(target_lab, token_lab)

            if dist < best_dist:
                best_dist = dist
                best_name = name
                best_hex = hex_val

        if not best_name:
            return None

        confidence = _classify_distance_color(best_dist)
        return TokenMatch(
            violation=violation,
            token_name=best_name,
            token_value=best_hex,
            distance=best_dist,
            confidence=confidence,
            suggestion=f"var(--{best_name})" if confidence != "far" else "",
        )

    # ------------------------------------------------------------------
    # Spacing matching (nearest pixel value)
    # ------------------------------------------------------------------
    def _match_spacing(self, violation: Violation) -> TokenMatch | None:
        """Match a pixel value to the nearest spacing token."""
        px = _extract_px(violation.original_value)
        if px is None:
            return None

        return self._match_numeric(
            violation, px, self.tokens.spacing_by_px,
            prefix="spacing-",
        )

    # ------------------------------------------------------------------
    # Font size matching
    # ------------------------------------------------------------------
    def _match_font_size(self, violation: Violation) -> TokenMatch | None:
        """Match a font-size to the nearest font-size token."""
        px = _extract_px(violation.original_value)
        if px is None:
            return None

        return self._match_numeric(
            violation, px, self.tokens.font_sizes_by_px,
            prefix="text-",
        )

    # ------------------------------------------------------------------
    # Z-index matching
    # ------------------------------------------------------------------
    def _match_z_index(self, violation: Violation) -> TokenMatch | None:
        """Match a z-index to the nearest token."""
        try:
            val = int(violation.original_value)
        except ValueError:
            return None

        best_name = ""
        best_val = 0
        best_dist = float("inf")

        for name, token_val in self.tokens.z_index.items():
            if token_val < 0:
                continue  # Skip sentinel values
            dist = abs(val - token_val)
            if dist < best_dist:
                best_dist = dist
                best_name = name
                best_val = token_val

        if not best_name:
            return None

        confidence = "exact" if best_dist == 0 else "close" if best_dist <= 5 else "approximate"
        return TokenMatch(
            violation=violation,
            token_name=f"z-{best_name}",
            token_value=str(best_val),
            distance=best_dist,
            confidence=confidence,
            suggestion=f"z-{best_name}",
        )

    # ------------------------------------------------------------------
    # Generic numeric matching
    # ------------------------------------------------------------------
    def _match_numeric(
        self,
        violation: Violation,
        value: float,
        lookup: dict[float, str],
        prefix: str = "",
    ) -> TokenMatch | None:
        """Match a numeric value to the nearest token."""
        best_name = ""
        best_px = 0.0
        best_dist = float("inf")

        for token_px, token_name in lookup.items():
            dist = abs(value - token_px)
            if dist < best_dist:
                best_dist = dist
                best_name = token_name
                best_px = token_px

        if not best_name:
            return None

        # Classify confidence based on distance
        if best_dist == 0:
            confidence = "exact"
        elif best_dist <= 2:
            confidence = "close"
        elif best_dist <= 4:
            confidence = "approximate"
        else:
            confidence = "far"

        return TokenMatch(
            violation=violation,
            token_name=f"{prefix}{best_name}",
            token_value=f"{best_px}px",
            distance=best_dist,
            confidence=confidence,
            suggestion=f"{prefix}{best_name}" if confidence != "far" else "",
        )


# ---------------------------------------------------------------------------
# Color parsing and LAB conversion utilities
# ---------------------------------------------------------------------------

def _parse_color(value: str) -> tuple[int, int, int] | None:
    """Parse a color string to RGB tuple."""
    value = value.strip()

    # Hex
    if value.startswith("#"):
        hex_str = value[1:]
        if len(hex_str) == 3:
            hex_str = "".join(c * 2 for c in hex_str)
        elif len(hex_str) == 4:
            hex_str = "".join(c * 2 for c in hex_str[:3])
        elif len(hex_str) == 8:
            hex_str = hex_str[:6]  # Drop alpha

        if len(hex_str) != 6:
            return None
        try:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return (r, g, b)
        except ValueError:
            return None

    # RGB
    import re
    rgb_m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', value)
    if rgb_m:
        return (int(rgb_m.group(1)), int(rgb_m.group(2)), int(rgb_m.group(3)))

    return None


def _rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB to CIELAB color space for perceptual distance."""
    # Normalize to 0-1
    r_n = r / 255.0
    g_n = g / 255.0
    b_n = b / 255.0

    # sRGB to linear
    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_l = linearize(r_n)
    g_l = linearize(g_n)
    b_l = linearize(b_n)

    # Linear RGB to XYZ (D65)
    x = r_l * 0.4124564 + g_l * 0.3575761 + b_l * 0.1804375
    y = r_l * 0.2126729 + g_l * 0.7151522 + b_l * 0.0721750
    z = r_l * 0.0193339 + g_l * 0.1191920 + b_l * 0.9503041

    # XYZ to Lab (D65 reference white)
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx = f(x / xn)
    fy = f(y / yn)
    fz = f(z / zn)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b_val = 200 * (fy - fz)

    return (L, a, b_val)


def _delta_e(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """Compute Delta-E (CIE76) perceptual color distance."""
    return math.sqrt(
        (lab1[0] - lab2[0]) ** 2 +
        (lab1[1] - lab2[1]) ** 2 +
        (lab1[2] - lab2[2]) ** 2
    )


def _classify_distance_color(dist: float) -> str:
    """Classify color distance into confidence levels."""
    if dist < 1:
        return "exact"
    elif dist < 5:
        return "close"
    elif dist < 15:
        return "approximate"
    return "far"


def _extract_px(value: str) -> float | None:
    """Extract pixel value from string like '13px' or '1.5rem'."""
    value = value.strip()
    if value.endswith("px"):
        try:
            return float(value[:-2])
        except ValueError:
            return None
    if value.endswith("rem") or value.endswith("em"):
        suffix_len = 3 if value.endswith("rem") else 2
        try:
            return float(value[:-suffix_len]) * 16
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None
