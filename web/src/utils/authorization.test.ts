import { describe, expect, it } from "vitest";
import { getAuthorization, removeAuthorization, setAuthorization } from "./authorization";

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
