import { afterEach, describe, expect, it, vi } from "vitest";
import { getAuthorization, onForeignTokenChange, removeAuthorization, setAuthorization, subscribeAuthorization } from "./authorization";

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

describe("unit authorization change detection across tabs (WR-F02)", () => {
  it("reports a removal from another tab with the previous and new value, not a local change", () => {
    setAuthorization("tok-a");
    const handler = vi.fn();
    const stop = onForeignTokenChange(handler);
    removeAuthorization();
    expect(handler).not.toHaveBeenCalled();
    setAuthorization("tok-a");
    localStorage.removeItem("Authorization");
    window.dispatchEvent(new StorageEvent("storage", { key: "Authorization" }));
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(null, "tok-a");
    stop();
  });

  it("reports a replaced token once and ignores a storage event that changed nothing", () => {
    setAuthorization("tok-a");
    const handler = vi.fn();
    const stop = onForeignTokenChange(handler);
    window.dispatchEvent(new StorageEvent("storage", { key: "Authorization" }));
    expect(handler).not.toHaveBeenCalled();
    localStorage.setItem("Authorization", "tok-b");
    window.dispatchEvent(new StorageEvent("storage", { key: "Authorization" }));
    window.dispatchEvent(new StorageEvent("storage", { key: "Authorization" }));
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith("tok-b", "tok-a");
    stop();
  });

  it("treats a cleared storage area (key null) as a removal", () => {
    setAuthorization("tok-a");
    const handler = vi.fn();
    const stop = onForeignTokenChange(handler);
    localStorage.clear();
    window.dispatchEvent(new StorageEvent("storage", { key: null }));
    expect(handler).toHaveBeenCalledWith(null, "tok-a");
    stop();
  });
});
