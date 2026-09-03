/**
 * Resolving design tokens to concrete colours at runtime.
 *
 * Most of the product styles itself from `var(--token)` in CSS, which is the
 * right thing and needs no help. SVG is the exception: charts and the
 * choropleth write colour into `fill` and `stroke` *attributes*, and `var()` is
 * only guaranteed to resolve inside a CSS property — so anything that ends up
 * in an attribute has to be looked up here first.
 *
 * Doing the lookup in JS also lets a token differ between themes and still be
 * correct, which matters for the categorical chart palette: no single mid-tone
 * set clears the 3:1 non-text contrast threshold against both a near-black and
 * a white ground, so light and dark define different values for `--series-N`.
 */

import { useEffect, useMemo, useState } from "react";
import { SERIES } from "./format";

const CSS_VAR = /^var\(\s*(--[\w-]+)\s*\)$/;

export interface ThemeColors {
  /** The categorical palette for the active theme, in `--series-N` order. */
  series: string[];
  /** Resolve a value that may be a `var(--token)` reference to a real colour. */
  resolve: (value: string | undefined, fallback?: string) => string;
}

function read(): ThemeColors {
  const styles = getComputedStyle(document.documentElement);
  const token = (name: string) => styles.getPropertyValue(name).trim();
  const series = SERIES.map((fallback, i) => token(`--series-${i + 1}`) || fallback);

  return {
    series,
    resolve(value, fallback = series[0]) {
      if (!value) return fallback;
      const match = CSS_VAR.exec(value.trim());
      if (!match) return value;
      return token(match[1]) || fallback;
    },
  };
}

/**
 * The resolved palette for the active theme. Recomputed when the theme
 * attribute on <html> changes, so charts and the map re-colour on toggle
 * instead of keeping the values they were first mounted with.
 */
export function useThemeColors(): ThemeColors {
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const observer = new MutationObserver(() => setRevision((r) => r + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(read, [revision]);
}
