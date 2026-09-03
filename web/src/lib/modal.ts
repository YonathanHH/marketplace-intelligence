/**
 * Focus management for modal overlays (the seller drawer, the mobile nav).
 *
 * An overlay that does not manage focus is only visually modal: Tab walks
 * straight out of it into the page behind, which someone using a screen reader
 * or a keyboard has no way to notice. This does the three things the dialog
 * pattern requires — move focus in, keep it in, and hand it back on close —
 * plus the two housekeeping jobs that go with them: Escape closes, and the
 * page behind stops scrolling.
 */

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useModalFocus<T extends HTMLElement>(
  active: boolean,
  onClose: () => void
): RefObject<T> {
  const ref = useRef<T>(null);

  // Held in a ref so a caller passing an inline arrow — which every caller
  // does — cannot re-run the effect on every render, tearing focus out of the
  // dialog and handing it back to the opener mid-interaction.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!active) return;

    const opener = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusable = () =>
      Array.from(ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
        (el) => el.offsetParent !== null
      );

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      // Only take focus back if it is still inside the dialog we are closing;
      // otherwise a click elsewhere on the page would get yanked away.
      if (!ref.current || ref.current.contains(document.activeElement)) {
        opener?.focus?.();
      }
    };
  }, [active]);

  return ref;
}
