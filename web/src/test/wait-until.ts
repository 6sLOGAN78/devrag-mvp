/**
 * The only permitted polling site in frontend tests (D-30). Tests wait for a
 * readiness predicate with a deadline instead of sleeping for a fixed time.
 */
export interface WaitUntilOptions {
  timeout?: number;
  interval?: number;
  describe?: string;
}

export async function waitUntil<T>(
  predicate: () => T | Promise<T>,
  { timeout = 15_000, interval = 100, describe = "condition" }: WaitUntilOptions = {},
): Promise<NonNullable<T>> {
  const deadline = Date.now() + timeout;
  let last: unknown;
  for (;;) {
    try {
      last = await predicate();
      if (last) return last as NonNullable<T>;
    } catch (error) {
      last = error;
    }
    if (Date.now() >= deadline) {
      throw new Error(`waitUntil timed out after ${timeout}ms waiting for ${describe}; last value: ${String(last)}`);
    }
    await new Promise<void>((resolve) => setTimeout(resolve, interval));
  }
}
