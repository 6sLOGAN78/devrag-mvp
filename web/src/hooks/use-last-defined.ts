import { useRef } from "react";

/**
 * The latest non-null value passed in. A confirmation dialog clears its target when it closes but stays on screen
 * for the exit animation, so its title and body read from the retained value instead of flashing empty.
 */
export function useLastDefined<T>(value: T | null): T | null {
  const last = useRef<T | null>(null);
  if (value !== null) last.current = value;
  return last.current;
}
