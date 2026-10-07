import { describe, expect, it } from "vitest";
import { loginSchema, NICKNAME_MAX, PASSWORD_MAX, PASSWORD_MIN, registerSchema } from "./schemas";

const email = "ada@example.test";

function issues(result: { success: boolean; error?: { issues: { message: string; path: (string | number)[] }[] } }) {
  return result.success ? [] : (result.error?.issues ?? []).map((i) => `${i.path.join(".")}:${i.message}`);
}

describe("shared constants", () => {
  it("mirror the server rule (D-02, D-29)", () => {
    expect(PASSWORD_MIN).toBe(8);
    expect(PASSWORD_MAX).toBe(128);
    expect(NICKNAME_MAX).toBe(64);
  });
});

describe("registerSchema password boundaries", () => {
  const parse = (password: string) => registerSchema.safeParse({ nickname: "Ada", email, password });

  it("rejects 7 characters with the min key", () => {
    expect(issues(parse("a".repeat(7)))).toEqual(["password:errors.password.min"]);
  });
  it("accepts 8 characters", () => {
    expect(parse("a".repeat(8)).success).toBe(true);
  });
  it("accepts 128 characters", () => {
    expect(parse("a".repeat(128)).success).toBe(true);
  });
  it("rejects 129 characters with the max key", () => {
    expect(issues(parse("a".repeat(129)))).toEqual(["password:errors.password.max"]);
  });
  it("counts characters, not UTF-16 units, and applies no composition rule", () => {
    expect(parse("😀".repeat(8)).success).toBe(true);
    expect(parse("😀".repeat(7)).success).toBe(false);
    expect(parse("        ").success).toBe(true);
  });
  it("does not trim the password", () => {
    const result = parse(" abcdefg ");
    expect(result.success && result.data.password).toBe(" abcdefg ");
  });
});

describe("email", () => {
  it("is trimmed and lowercased", () => {
    const result = loginSchema.safeParse({ email: "  Ada@Example.TEST ", password: "x" });
    expect(result.success && result.data.email).toBe("ada@example.test");
  });
  it("requires a value and a valid address", () => {
    expect(issues(loginSchema.safeParse({ email: "  ", password: "x" }))).toEqual(["email:errors.email.required"]);
    for (const bad of ["ada", "ada@", "@example.test", "ada@@example.test", "ada@localhost", "a b@example.test"]) {
      expect(issues(loginSchema.safeParse({ email: bad, password: "x" })), bad).toEqual(["email:errors.email.invalid"]);
    }
  });
  it("rejects more than 255 characters like the server", () => {
    const long = `${"a".repeat(250)}@example.test`;
    expect(issues(loginSchema.safeParse({ email: long, password: "x" }))).toEqual(["email:errors.email.invalid"]);
  });
});

describe("loginSchema", () => {
  it("requires a password but applies no length rule (an old short password must still be able to sign in)", () => {
    expect(issues(loginSchema.safeParse({ email, password: "" }))).toEqual(["password:errors.password.required"]);
    expect(loginSchema.safeParse({ email, password: "short" }).success).toBe(true);
  });
});

describe("registerSchema nickname", () => {
  const parse = (nickname: string) => registerSchema.safeParse({ nickname, email, password: "password-1" });
  it("is trimmed and required", () => {
    expect(issues(parse("   "))).toEqual(["nickname:errors.nickname.required"]);
    const ok = parse("  Ada  ");
    expect(ok.success && ok.data.nickname).toBe("Ada");
  });
  it("allows 64 characters and rejects 65", () => {
    expect(parse("n".repeat(64)).success).toBe(true);
    expect(issues(parse("n".repeat(65)))).toEqual(["nickname:errors.nickname.max"]);
  });
  it("rejects angle brackets, control and format characters like the server", () => {
    for (const bad of ["<b>x</b>", "a>b", "tab\there", "a‮b", "a​b"]) {
      expect(issues(parse(bad)), JSON.stringify(bad)).toEqual(["nickname:errors.nickname.invalid"]);
    }
  });
  it("accepts non-latin names", () => {
    expect(parse("阿达").success).toBe(true);
  });
});
