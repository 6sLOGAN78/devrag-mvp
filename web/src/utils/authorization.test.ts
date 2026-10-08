import { afterEach, describe, expect, it, vi } from "vitest";
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

function blockStorage(): void {
  const denied = () => {
    throw new DOMException("The operation is insecure.", "SecurityError");
  };
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(denied);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(denied);
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(denied);
}

describe("unit authorization with blocked storage (WR-F01)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    removeAuthorization();
  });

  it("reads null instead of throwing when storage access is denied", () => {
    blockStorage();
    expect(() => getAuthorization()).not.toThrow();
    expect(getAuthorization()).toBeNull();
  });

  it("keeps the token in memory for the tab's lifetime when storage cannot be written", () => {
    blockStorage();
    const listener = vi.fn();
    const unsubscribe = subscribeAuthorization(listener);
    expect(() => setAuthorization("tok")).not.toThrow();
    expect(getAuthorization()).toBe("tok");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(() => removeAuthorization()).not.toThrow();
    expect(getAuthorization()).toBeNull();
    unsubscribe();
  });

  it("keeps the token in memory when only the write is refused (quota or policy)", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    setAuthorization("tok");
    expect(getAuthorization()).toBe("tok");
    removeAuthorization();
    expect(getAuthorization()).toBeNull();
  });
});
