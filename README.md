# rogue-css-sniper

Hunt down hardcoded CSS values and snap them to design system tokens.

## Features

- **Multi-format scanning** -- CSS, SCSS, TSX, JSX, Vue, Svelte files
- **Color detection** -- Hex (#abc, #aabbcc), RGB, HSL values matched via Delta-E perceptual distance in CIELAB space
- **Spacing detection** -- Hardcoded pixel values (13px, 17px) matched to nearest token
- **Font-size detection** -- Hardcoded font sizes flagged and matched
- **Z-index detection** -- Non-standard z-index values caught
- **Built-in Tailwind v3 tokens** -- Full default palette, spacing, font sizes out of the box
- **Custom token support** -- Load from JSON/YAML (Style Dictionary, Tailwind config, flat format)
- **Auto-fix** -- Replace hardcoded values with CSS custom property references (interactive or batch)
- **Reports** -- Terminal table (Rich), JSON, markdown with stats

## Installation

```bash
pip install rogue-css-sniper
```

Or from source:

```bash
git clone https://github.com/yourusername/rogue-css-sniper.git
cd rogue-css-sniper
pip install -e .
```

## Usage

```bash
# Scan a directory for violations
rogue-css-sniper scan ./src

# Scan with custom design tokens
rogue-css-sniper scan ./src --tokens design-tokens.json

# Preview fixes (dry run)
rogue-css-sniper fix ./src --dry-run

# Auto-fix with interactive mode
rogue-css-sniper fix ./src --interactive

# Auto-fix (exact and close matches only)
rogue-css-sniper fix ./src --min-confidence close

# Generate reports
rogue-css-sniper report ./src --format json --output report.json
rogue-css-sniper report ./src --format markdown --output report.md
```

## Token Formats Supported

### Tailwind config (built-in)
Default Tailwind v3 colors, spacing, font-sizes, z-index loaded automatically.

### Custom JSON/YAML
```json
{
  "colors": {
    "primary": "#0969da",
    "danger": "#dc3545"
  },
  "spacing": {
    "sm": "8px",
    "md": "16px",
    "lg": "24px"
  },
  "fontSize": {
    "body": "16px",
    "heading": "24px"
  }
}
```

### Style Dictionary format
```json
{
  "color": {
    "primary": { "$value": "#0969da", "$type": "color" },
    "danger": { "$value": "#dc3545", "$type": "color" }
  }
}
```

## How Matching Works

- **Colors**: Converted to CIELAB color space, matched by Delta-E perceptual distance
  - Exact: < 1 Delta-E (imperceptible difference)
  - Close: < 5 Delta-E (barely noticeable)
  - Approximate: < 15 Delta-E (visible difference)
- **Spacing/Font-size**: Matched to nearest pixel value in token set
- **Z-index**: Matched to nearest standard value (0, 10, 20, 30, 40, 50)

## License

MIT
