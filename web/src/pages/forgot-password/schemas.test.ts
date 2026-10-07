import { describe, expect, it } from "vitest";
import { codeStepSchema, emailStepSchema, passwordStepSchema } from "./schemas";

function issues(result: { success: boolean; error?: { issues: { message: string; path: (string | number)[] }[] } }) {
  return result.success ? [] : (result.error?.issues ?? []).map((i) => `${i.path.join(".")}:${i.message}`);
}

describe("emailStepSchema", () => {
  it("accepts a valid address and normalises it", () => {
    const parsed = emailStepSchema.safeParse({ email: "  Ada@Example.test " });
    expect(parsed.success && parsed.data.email).toBe("ada@example.test");
  });
  it("rejects empty and malformed input with the shared keys", () => {
    expect(issues(emailStepSchema.safeParse({ email: "" }))).toEqual(["email:errors.email.required"]);
    expect(issues(emailStepSchema.safeParse({ email: "not-an-email" }))).toEqual(["email:errors.email.invalid"]);
  });
});

describe("codeStepSchema", () => {
  const parse = (code: string) => codeStepSchema.safeParse({ code });
  it("accepts exactly six digits", () => {
    expect(parse("123456").success).toBe(true);
    expect(parse("000000").success).toBe(true);
  });
  it("rejects 5 digits, 7 digits, letters, spaces and the empty string", () => {
    for (const bad of ["12345", "1234567", "12345a", "abcdef", "123 456", ""]) {
      expect(issues(parse(bad))).toEqual(["code:errors.code.invalid"]);
    }
  });
});

describe("passwordStepSchema", () => {
  const parse = (password: string) => passwordStepSchema.safeParse({ password });
  it("enforces 8 to 128 characters, never trimmed", () => {
    expect(issues(parse("a".repeat(7)))).toEqual(["password:errors.password.min"]);
    expect(parse("a".repeat(8)).success).toBe(true);
    expect(parse("a".repeat(128)).success).toBe(true);
    expect(issues(parse("a".repeat(129)))).toEqual(["password:errors.password.max"]);
    expect(parse("        ").success).toBe(true);
  });
});
