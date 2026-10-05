import { describe, expect, it } from "vitest";
import { waitUntil } from "./wait-until";

describe("waitUntil", () => {
  it("returns the first truthy value", async () => {
    let calls = 0;
    const value = await waitUntil(() => (++calls >= 3 ? "ready" : null), { interval: 1 });
    expect(value).toBe("ready");
    expect(calls).toBe(3);
  });

  it("treats a throwing predicate as not ready yet", async () => {
    let calls = 0;
    const value = await waitUntil(
      () => {
        if (++calls < 2) throw new Error("not yet");
        return 42;
      },
      { interval: 1 },
    );
    expect(value).toBe(42);
  });

  it("rejects with the timeout and last value", async () => {
    await expect(waitUntil(() => false, { timeout: 30, interval: 5, describe: "never" })).rejects.toThrow(
      /timed out after 30ms waiting for never; last value: false/,
    );
  });
});
