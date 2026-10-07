import { describe, expect, it, vi } from "vitest";
import { getAuthorization, removeAuthorization, setAuthorization, subscribeAuthorization } from "./authorization";

describe("unit authorization util", () => {
  it("returns null when no token is stored", () => {
    expect(getAuthorization()).toBeNull();
  });

  it("stores and reads the token", () => {
    setAuthorization("abc");
    expect(getAuthorization()).toBe("abc");
  });

  it("removes the token", () => {
    setAuthorization("abc");
    removeAuthorization();
    expect(getAuthorization()).toBeNull();
  });
});

describe("unit authorization subscription", () => {
  it("notifies listeners when the token is set or removed and stops after unsubscribe", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuthorization(listener);
    setAuthorization("abc");
    removeAuthorization();
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    setAuthorization("def");
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("notifies on a storage event for the token key from another tab, not for other keys", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuthorization(listener);
    window.dispatchEvent(new StorageEvent("storage", { key: "Authorization" }));
    window.dispatchEvent(new StorageEvent("storage", { key: "theme" }));
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});
