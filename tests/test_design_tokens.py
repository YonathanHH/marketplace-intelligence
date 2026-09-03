"""Colour contrast, asserted rather than eyeballed.

Every token used for text has to clear WCAG AA (4.5:1) against every surface it
can sit on, in both themes. That is easy to get right once and easy to break
later with a plausible-looking tweak, so it is checked here against the actual
token values in `tokens.css`.

The previous palette failed this in eleven places — most of the light theme's
semantic colours, and `--text-faint`, which carries the smallest text in the
product — which is why the check exists.
"""

from __future__ import annotations

import re

import pytest

from olxads.config import PROJECT_ROOT

TOKENS_CSS = PROJECT_ROOT / "web" / "src" / "styles" / "tokens.css"

# Tokens rendered as text, and every background they can appear on.
TEXT_TOKENS = [
    "--text", "--text-muted", "--text-faint",
    "--accent", "--success", "--warning", "--danger", "--info",
    "--tier-hot", "--tier-warm", "--tier-cool", "--tier-low",
]
SURFACES = ["--bg", "--bg-subtle", "--surface", "--surface-raised", "--surface-hover"]

# Chart series are graphical objects, not text: WCAG 1.4.11 asks for 3:1.
SERIES_TOKENS = [f"--series-{i}" for i in range(1, 10)]

AA_TEXT = 4.5
AA_NON_TEXT = 3.0


def _relative_luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_block(css: str, selector: str) -> dict[str, str]:
    """Pull the `--token: #hex;` declarations out of one rule."""
    start = css.index(selector)
    block = css[start:css.index("}", start)]
    return {
        name: value
        for name, value in re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block)
    }


@pytest.fixture(scope="module")
def themes() -> dict[str, dict[str, str]]:
    css = TOKENS_CSS.read_text(encoding="utf-8")
    return {
        "dark": _parse_block(css, ":root,\n[data-theme=\"dark\"]"),
        "light": _parse_block(css, '[data-theme="light"]'),
    }


def test_both_themes_define_every_token(themes):
    for theme, tokens in themes.items():
        missing = [t for t in TEXT_TOKENS + SURFACES + SERIES_TOKENS if t not in tokens]
        assert not missing, f"{theme} theme is missing {missing}"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_text_tokens_meet_wcag_aa(themes, theme):
    tokens = themes[theme]
    failures = []
    for token in TEXT_TOKENS:
        for surface in SURFACES:
            ratio = contrast_ratio(tokens[token], tokens[surface])
            if ratio < AA_TEXT:
                failures.append(f"{token} on {surface}: {ratio:.2f}:1")
    assert not failures, f"{theme} theme below 4.5:1 -> " + "; ".join(failures)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_chart_series_meet_non_text_contrast(themes, theme):
    tokens = themes[theme]
    failures = [
        f"{token}: {contrast_ratio(tokens[token], tokens['--surface']):.2f}:1"
        for token in SERIES_TOKENS
        if contrast_ratio(tokens[token], tokens["--surface"]) < AA_NON_TEXT
    ]
    assert not failures, f"{theme} chart series below 3:1 on --surface -> " + "; ".join(failures)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_accent_buttons_are_legible(themes, theme):
    """`--on-accent` is what sits on a filled accent button; plain white fails
    against the dark theme's bright teal, which is why the token exists."""
    tokens = themes[theme]
    ratio = contrast_ratio(tokens["--on-accent"], tokens["--accent"])
    assert ratio >= AA_TEXT, f"{theme}: --on-accent on --accent is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_map_ramp_bins_are_distinguishable(themes, theme):
    """Adjacent choropleth bins must actually differ, or the map encodes nothing."""
    tokens = themes[theme]
    ramp = [tokens[f"--map-{i}"] for i in range(1, 6)]
    for lower, upper in zip(ramp, ramp[1:]):
        ratio = contrast_ratio(lower, upper)
        assert ratio >= 1.2, f"{theme}: adjacent map bins {lower}/{upper} differ by only {ratio:.2f}:1"


def test_no_component_hardcodes_a_hex_colour():
    """Components style themselves from tokens. A stray hex is how a theme
    silently stops working in one of its two modes."""
    src = PROJECT_ROOT / "web" / "src"
    offenders = []
    for path in list(src.rglob("*.tsx")) + list(src.rglob("*.ts")):
        # format.ts holds the documented fallback palette for when the tokens
        # cannot be read; everything else must go through a var().
        if path.name == "format.ts":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{6}\b", line):
                offenders.append(f"{path.relative_to(src).as_posix()}:{number}: {line.strip()}")
    assert not offenders, "hardcoded colours found:\n  " + "\n  ".join(offenders)
