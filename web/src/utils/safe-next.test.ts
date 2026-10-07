import { describe, expect, it } from "vitest";
import { HOME_PATH, loginRedirect, sanitiseNext } from "./safe-next";

describe("sanitiseNext (open-redirect guard, T-02-49)", () => {
  it.each([
    ["/user-setting/api?x=1", "/user-setting/api?x=1"],
    ["/", "/"],
    ["/system-status", "/system-status"],
    ["/a/b#frag", "/a/b#frag"],
  ])("accepts the internal path %s", (input, expected) => {
    expect(sanitiseNext(input)).toBe(expected);
  });

  it.each([
    ["protocol-relative //evil.com", "//evil.com"],
    ["backslash after the slash", "/\\evil.com"],
    ["double backslash", "\\\\evil.com"],
    ["absolute https URL", "https://evil.com"],
    ["absolute http URL", "http://evil.com/x"],
    ["javascript scheme", "javascript:alert(1)"],
    ["data scheme", "data:text/html,x"],
    ["empty string", ""],
    ["undefined", undefined],
    ["null", null],
    ["trailing newline", "/home\n"],
    ["embedded tab that browsers strip", "/\t/evil.com"],
    ["carriage return", "/\r/evil.com"],
    ["relative path without a slash", "home"],
    ["leading space", " /home"],
    ["over 512 characters", `/${"a".repeat(512)}`],
  ])("falls back to the home route for %s", (_name, input) => {
    expect(sanitiseNext(input)).toBe(HOME_PATH);
  });

  it("accepts a path of exactly 512 characters", () => {
    const path = `/${"a".repeat(511)}`;
    expect(sanitiseNext(path)).toBe(path);
  });
});

describe("loginRedirect", () => {
  it("encodes the current path and search into next", () => {
    expect(loginRedirect("/user-setting/profile")).toBe("/login?next=%2Fuser-setting%2Fprofile");
    expect(loginRedirect("/a?b=1&c=2")).toBe("/login?next=%2Fa%3Fb%3D1%26c%3D2");
  });

  it("drops next when the current path is already a public auth page", () => {
    expect(loginRedirect("/login")).toBe("/login");
    expect(loginRedirect("/login?next=%2Fx")).toBe("/login");
    expect(loginRedirect("/forgot-password")).toBe("/login");
  });

  it("never carries an unsafe target", () => {
    expect(loginRedirect("//evil.com")).toBe("/login");
  });
});
