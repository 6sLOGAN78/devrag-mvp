import { AxiosError, CanceledError } from "axios";
import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import en from "@/locales/en.json";
import { ApiError } from "@/services/http";
import { deleteFailureKey, isAborted, providerErrorKey } from "./errors";

type Tree = { [k: string]: string | Tree };

function lookup(key: string): string {
  let node: string | Tree | undefined = en as Tree;
  for (const part of key.split(".")) node = typeof node === "object" ? node[part] : undefined;
  if (typeof node !== "string") throw new Error(`missing en.json key ${key}`);
  return node;
}

const api = (status: number, reason?: string, message = "", extra: { retryAfter?: number } = {}) =>
  new ApiError({ code: status === 400 ? 101 : status, message, status, data: reason === undefined ? null : { reason }, ...extra });

describe("providerErrorKey (UI-SPEC checker flags 2 and 3)", () => {
  it("shows the provider's own reason for a refusal and keeps the refusal title", () => {
    expect(providerErrorKey(api(400, "provider_refused", "The provider rejected the key"))).toEqual({ key: "models.refused.fallback", text: "The provider rejected the key", refusal: true });
  });

  it("falls back for an empty, blank or over-long refusal text", () => {
    expect(providerErrorKey(api(400, "provider_refused", ""))).toEqual({ key: "models.refused.fallback", refusal: true });
    expect(providerErrorKey(api(400, "provider_refused", "   "))).toEqual({ key: "models.refused.fallback", refusal: true });
    expect(providerErrorKey(api(400, "provider_refused", "x".repeat(301)))).toEqual({ key: "models.refused.fallback", refusal: true });
    expect(providerErrorKey(api(400, "provider_refused", "x".repeat(300))).text).toBe("x".repeat(300));
  });

  it.each([
    [429, "provider_test_rate_limited", "models.rateLimited"],
    [503, "provider_rate_limited", "models.providerBusy"],
    [503, "key_store_unavailable", "models.keyStoreDown"],
    [503, "rate_limit_unavailable", "models.keyStoreDown"],
    [503, "something_new", "models.keyStoreDown"],
    [504, "provider_timeout", "models.timeout"],
    [502, "provider_unreachable", "models.providerDown"],
    [403, undefined, "workspace.forbidden"],
    [409, "model_exists", "models.error.modelExists"],
    [400, "base_url_refused", "models.error.addressRefused"],
    [400, "dimension_mismatch", "models.error.dimension"],
    [400, "dimension_unsupported", "models.error.dimension"],
    [500, undefined, "models.refused.generic"],
    [404, undefined, "models.refused.generic"],
    [400, "models_invalid", "models.refused.generic"],
    [400, "never_heard_of_it", "models.refused.generic"],
  ] as const)("maps %i %s to %s", (status, reason, key) => {
    const result = providerErrorKey(api(status, reason, "server words that must not be shown"));
    expect(result.key).toBe(key);
    expect(result.text).toBeUndefined();
    expect(result.refusal).toBe(false);
  });

  it("puts a key that is needed for a new address under the key field", () => {
    expect(providerErrorKey(api(400, "key_required_for_new_address", "enter the key again to use a different address"))).toEqual({
      key: "errors.provider.keyNewAddress",
      field: "key",
      refusal: false,
    });
    expect(providerErrorKey(api(400, "key_required"))).toEqual({ key: "errors.provider.keyRequired", field: "key", refusal: false });
  });

  it("tells a client timeout from a network failure", () => {
    const timedOut = new ApiError({ code: -1, status: 0, message: i18n.t("toast.timeout.title") });
    const offline = new ApiError({ code: -1, status: 0, message: i18n.t("toast.network.title") });
    expect(providerErrorKey(timedOut).key).toBe("models.timeout");
    expect(providerErrorKey(offline).key).toBe("models.providerDown");
    expect(providerErrorKey(new AxiosError("timeout", "ECONNABORTED")).key).toBe("models.timeout");
    expect(providerErrorKey(new AxiosError("down", "ERR_NETWORK")).key).toBe("models.providerDown");
  });

  it("gives anything else, including a non-error, the generic copy", () => {
    expect(providerErrorKey(new Error("boom"))).toEqual({ key: "models.refused.generic", refusal: false });
    expect(providerErrorKey(undefined)).toEqual({ key: "models.refused.generic", refusal: false });
  });

  it("never turns a 401 into session wording or server text", () => {
    const result = providerErrorKey(api(401, undefined, "Unauthorized: session expired"));
    expect(result).toEqual({ key: "models.refused.generic", refusal: false });
  });

  it("ignores server text on every kind except a provider refusal", () => {
    for (const status of [403, 409, 429, 500, 502, 503, 504]) expect(providerErrorKey(api(status, "x_reason", "server words")).text).toBeUndefined();
  });

  it("copy for every answer avoids the words session, sign in and unauthorized", () => {
    const answers = [
      api(400, "provider_refused"),
      api(429, "provider_test_rate_limited"),
      api(503, "provider_rate_limited"),
      api(503, "key_store_unavailable"),
      api(504),
      api(502),
      api(403),
      api(401),
      api(500),
      api(409, "model_exists"),
      api(400, "key_required_for_new_address"),
      new ApiError({ code: -1, status: 0, message: "x" }),
    ];
    for (const answer of answers) expect(lookup(providerErrorKey(answer).key)).not.toMatch(/session|sign in|unauthori[sz]ed/i);
    expect(lookup(deleteFailureKey())).not.toMatch(/session|sign in|unauthori[sz]ed/i);
    expect(lookup("models.testing")).not.toMatch(/session|sign in|unauthori[sz]ed/i);
  });
});

describe("isAborted", () => {
  it("is true for a cancelled request and false for a failure", () => {
    expect(isAborted(new CanceledError("canceled"))).toBe(true);
    expect(isAborted(api(500))).toBe(false);
    expect(isAborted(undefined)).toBe(false);
  });
});

describe("test duration wording agrees with the timeouts (checker flag 5)", () => {
  it("says up to 40 seconds: two server tests of 20 seconds each, under the 45 second client timeout", () => {
    expect(lookup("models.testing")).toContain("40 seconds");
  });
});
