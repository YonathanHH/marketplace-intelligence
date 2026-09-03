# UI engineering notes

The frontend is Vite + React + TypeScript with no component library and no CSS
framework: ~30 KB of CSS built on a token file, and primitives in
`web/src/components/ui.tsx`. This documents the decisions that are not obvious
from the code, and the accessibility work that is enforced by tests.

## Design tokens

`web/src/styles/tokens.css` is the single source of truth. Components never
hardcode a colour — `tests/test_design_tokens.py::test_no_component_hardcodes_a_hex_colour`
fails the build if one appears.

### Contrast is asserted, not eyeballed

Every token used for **text** clears WCAG AA (4.5:1) against every surface it
can appear on, in **both** themes. Tokens used only as **fills** (chart series,
map bins) clear the 3:1 non-text threshold. Both are checked in CI against the
parsed token values.

The check was added because the palette failed it in eleven places. `--text-faint`
— which carries the smallest text in the product (table subtitles, card
subtitles, timeline metadata) — sat at 3.8:1 in dark and **2.8:1 in light**, and
almost every semantic colour in the light theme failed as text:

| Token | Old (light, on `--surface`) | Now |
|---|---|---|
| `--text-faint` | 3.03:1 | 4.72:1 |
| `--success` | 3.87:1 | 5.32:1 |
| `--warning` | 3.43:1 | 5.48:1 |
| `--danger` | 4.72:1 | 4.83:1 |
| `--tier-warm` | 3.43:1 | 5.48:1 |

### The palette moved off indigo

The accent was `#7c6bff`. Purple-indigo on near-black is the default look of
generated UI, and it carried no relationship to the product. It is now a deep
teal — `#2ed3c3` in dark, `#0d6f6c` in light — which reads as a marketplace
analytics tool rather than a template, and clears AA in both directions.

Two follow-ons this forced, both correct anyway:

- **`--on-accent`.** `.btn-primary` hardcoded `color: #fff`, which fails against
  a bright teal fill. Filled accent surfaces now use `--on-accent` (near-black in
  dark, white in light), asserted at 4.5:1 against `--accent`.
- **The brand mark is flat.** It was a two-stop gradient into a colour that
  existed nowhere else in the system.

### Chart colour has to be resolved in JS

`web/src/lib/theme.ts` reads tokens off the document and hands back concrete
values. Two reasons, and the first is a correctness bug rather than a preference:

1. Recharts and the choropleth write colour into SVG **`fill` / `stroke`
   attributes**, where `var(--token)` does not reliably resolve. It only
   resolves inside a CSS property.
2. The categorical palette **differs between themes**. It has to: no single
   mid-tone set clears 3:1 against both a near-black and a white ground. The
   nine `--series-N` tokens are defined per theme, and `useThemeColors`
   re-reads them via a `MutationObserver` on `data-theme`, so charts re-colour
   on toggle instead of keeping the values they mounted with.

## Accessibility

### Navigation existed only above 860px

`.sidebar { display: none }` below the breakpoint left the product with **no
navigation at all** on a phone. The same nav is now an overlay dialog behind a
topbar trigger, rendered only while open so its links stay out of the tab order
otherwise.

### Focus management

`web/src/lib/modal.ts` handles the seller drawer and the mobile nav: move focus
in, trap Tab, restore to the opener, Escape to close, lock body scroll. `onClose`
is held in a ref — every caller passes an inline arrow, and depending on it
directly would re-run the effect on every render and yank focus out of the
dialog mid-interaction.

### Tables

- Sort controls are **`<button>` inside `<th>`** with `aria-sort` on the cell.
  They were `onClick` handlers on the `<th>`: not focusable, not activatable
  from a keyboard, with the sort state conveyed only by an arrow glyph.
- Rows are clickable for a pointer, but the **first cell is a real `<Link>`** —
  that is what a keyboard lands on, and it names the row. The cell is
  `<th scope="row">`, so a screen reader announces which seller each value
  belongs to.
- `TableScroll` gives the horizontal scroll container `tabindex="0"`, `role="region"`
  and a name. A scrollable region has to be reachable by keyboard (WCAG 2.1.1).

### Charts

Every chart takes a required `label` prop and renders inside `role="img"`.
A bare `<svg>` of paths conveys nothing. The rule the codebase follows: **a
chart is never the only place a number appears** — each one sits beside a table,
a bar list, or a definition list carrying the same values.

### Native tooltips are gone

`Kpi` took a `tooltip` prop rendered as `title=""`. Native tooltips never appear
for keyboard or touch users. It is now `hint`, rendered as visible text under a
rule. Same change on the map legend, where the bin boundaries were `title`
attributes — the ramp is meaningless without them.

### Other

- Skip link, first in the tab order on every route.
- `<main id="main-content">`, `<nav aria-label="Primary">`, and `document.title`
  updated per route — a client-side navigation otherwise gives none of the cues
  a real one does.
- Live regions for filter results and the activity form's outcome.
- Icons are `aria-hidden` by default; they are always beside a label or inside a
  control with its own name.
- Theme follows `prefers-color-scheme` until the user chooses explicitly, and is
  stamped by an inline script before first paint so there is no flash.
- 32px minimum hit target on every control (WCAG 2.5.8).
- `forced-colors` block so Windows High Contrast keeps card and control borders.

## Responsive

Tested at 320, 480, 768, 1024 and 1440. Breakpoints:

| Width | Change |
|---|---|
| ≤1280px | Multi-column grids collapse to two; split layouts stack |
| ≤860px | Sidebar → overlay nav; grids to one column; drawer full-width; tabs scroll |
| ≤480px | Tighter padding, smaller KPI type, pagination wraps |

Wide tables scroll inside their own focusable region rather than forcing the
page to scroll sideways.
