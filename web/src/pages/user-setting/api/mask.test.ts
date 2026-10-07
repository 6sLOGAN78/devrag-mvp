import { describe, expect, it } from "vitest";
import { MASK_BULLETS, MASK_PREFIX, MASK_TAIL_LENGTH, maskToken, tokenTail } from "./mask";

// Obviously fake values: no real token is ever written into a test.
const FAKE = "ragflow-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789FAKE-xyz9";

describe("token masking rule (UI-35, UI checker flag 6)", () => {
  it("states the rule as constants: the 8 character prefix, eight bullets and a tail of four", () => {
    expect(MASK_PREFIX).toBe("ragflow-");
    expect(MASK_PREFIX).toHaveLength(8);
    expect(MASK_BULLETS).toBe("•".repeat(8));
    expect(MASK_TAIL_LENGTH).toBe(4);
  });

  it("masks as the literal prefix, eight bullets and the last four characters", () => {
    expect(maskToken(FAKE)).toBe(`ragflow-${"•".repeat(8)}xyz9`);
  });

  it("never lets the middle of the token into the masked text", () => {
    const masked = maskToken(FAKE);
    expect(masked).not.toContain("AbCdEf");
    expect(masked).not.toContain("FAKE");
    expect(masked).toHaveLength(8 + 8 + 4);
  });

  it("returns the last four characters as the tail", () => {
    expect(tokenTail(FAKE)).toBe("xyz9");
  });

  it.each(["", "a", "ragflow-abc", "ragflow-abcd"])("fully masks the short or odd value %j without throwing and without echoing its tail", (value) => {
    expect(maskToken(value)).toBe("•".repeat(MASK_PREFIX.length + MASK_BULLETS.length + MASK_TAIL_LENGTH));
    expect(tokenTail(value)).toBe("•".repeat(MASK_TAIL_LENGTH));
  });

  it("fully masks a long value that does not start with the prefix instead of printing a wrong prefix", () => {
    const masked = maskToken("other-AbCdEfGhIjKlMnOpQrStUvWxYz0123");
    expect(masked).not.toContain("other");
    expect(masked).not.toContain("ragflow");
  });
});
