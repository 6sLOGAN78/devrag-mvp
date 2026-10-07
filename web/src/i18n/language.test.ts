import { describe, expect, it } from "vitest";
import { detectLanguage, LANG_KEY, normalizeLanguage } from "@/i18n/language";

describe("normalizeLanguage", () => {
  it("maps Chinese spellings to zh", () => {
    for (const v of ["zh", "zh-CN", "zh-Hans-CN", "ZH", "Chinese"]) expect(normalizeLanguage(v)).toBe("zh");
  });
  it("maps English spellings, unknown and empty values to en", () => {
    for (const v of ["en", "en-US", "English", "fr", "", null, undefined]) expect(normalizeLanguage(v)).toBe("en");
  });
});

describe("detectLanguage", () => {
  it("prefers the user language over the stored choice", () => {
    expect(detectLanguage({ userLanguage: "Chinese", stored: "en", navigatorLanguage: "en-US" })).toBe("zh");
    expect(detectLanguage({ userLanguage: "English", stored: "zh", navigatorLanguage: "zh-CN" })).toBe("en");
  });
  it("prefers the stored choice over the browser language", () => {
    expect(detectLanguage({ stored: "zh", navigatorLanguage: "en-US" })).toBe("zh");
    expect(detectLanguage({ stored: "en", navigatorLanguage: "zh-CN" })).toBe("en");
  });
  it("falls back to the browser language, then English", () => {
    expect(detectLanguage({ navigatorLanguage: "zh-TW" })).toBe("zh");
    expect(detectLanguage({ navigatorLanguage: "de-DE" })).toBe("en");
    expect(detectLanguage({})).toBe("en");
  });
  it("uses the documented storage key", () => {
    expect(LANG_KEY).toBe("devrag.lang");
  });
});
