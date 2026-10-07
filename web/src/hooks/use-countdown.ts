import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Whole-second countdown. The deadline is a clock time, so a throttled background tab catches up instead of
 * drifting. The interval exists only while the countdown runs and is cleared on unmount.
 */
export function useCountdown(initialSeconds: number) {
  const [remaining, setRemaining] = useState(initialSeconds);
  const deadline = useRef(Date.now() + initialSeconds * 1000);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current !== null) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const start = useCallback(
    (seconds: number) => {
      stop();
      deadline.current = Date.now() + seconds * 1000;
      setRemaining(seconds);
      timer.current = setInterval(() => {
        const left = Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000));
        setRemaining(left);
        if (left === 0) stop();
      }, 1000);
    },
    [stop],
  );

  useEffect(() => {
    start(initialSeconds);
    return stop;
    // The countdown starts once per mount; later restarts go through `start`.
  }, []);

  return { remaining, start };
}
