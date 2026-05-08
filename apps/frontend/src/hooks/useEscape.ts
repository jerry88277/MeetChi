"use client";

import { useEffect } from "react";

/**
 * Listen for Escape key while `enabled` is true and run `onEscape`.
 *
 * Used by Modal / Drawer / Dropdown components to give users a consistent
 * way to dismiss overlays. Auto-detaches on unmount or when `enabled` flips
 * to false, so multiple stacked overlays each manage their own escape
 * lifecycle.
 *
 * @example
 *   const [open, setOpen] = useState(false);
 *   useEscape(() => setOpen(false), open);
 */
export function useEscape(onEscape: () => void, enabled: boolean = true): void {
    useEffect(() => {
        if (!enabled) return;

        const handler = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.stopPropagation();
                onEscape();
            }
        };

        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [onEscape, enabled]);
}
