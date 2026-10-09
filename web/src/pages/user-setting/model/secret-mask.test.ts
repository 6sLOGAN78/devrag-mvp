import { describe, expect, it } from "vitest";
import { maskSecret } from "./secret-mask";

describe("maskSecret (D-07, UI-SPEC choice 24)", () => {
  it("is eight bullets plus the four characters the server supplied", () => {
    expect(maskSecret("ab12")).toBe("••••••••ab12");
  });

  it("gives eight bullets and nothing else when the tail is missing or short", () => {
    expect(maskSecret("")).toBe("••••••••");
    expect(maskSecret("ab")).toBe("••••••••");
    expect(maskSecret(undefined as unknown as string)).toBe("••••••••");
    expect(maskSecret(null as unknown as string)).toBe("••••••••");
  });

  it("never shows more than four characters, even when given more", () => {
    expect(maskSecret("sk-FAKE-1234567890wxyz")).toBe("••••••••wxyz");
  });

  it("never throws on non-string input", () => {
    expect(() => maskSecret(42 as unknown as string)).not.toThrow();
    expect(maskSecret(42 as unknown as string)).toBe("••••••••");
  });
});
