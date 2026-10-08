import { AxiosHeaders, type AxiosAdapter } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ApiError, http } from "./http";
import { createApiToken } from "./api-token-service";
import { inviteMember } from "./team-service";
import { getUserInfo } from "./user-service";

const originalAdapter = http.defaults.adapter;
let body: unknown;

const adapter: AxiosAdapter = (config) =>
  Promise.resolve({ data: body, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

beforeEach(() => {
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});

const successWith = (data: unknown) => ({ code: 0, message: "", data });

describe("service mappers on a malformed success body (IN-F07)", () => {
  const cases: Array<[string, () => Promise<unknown>]> = [
    ["getUserInfo", () => getUserInfo()],
    ["inviteMember", () => inviteMember("t1", "a@example.test")],
    ["createApiToken", () => createApiToken()],
  ];

  it.each(cases)("%s rejects with a clear ApiError, not a TypeError, when data is null", async (_name, call) => {
    body = successWith(null);
    const error = await call().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(TypeError);
    expect(error).toMatchObject({ code: -1 });
  });

  it.each(cases)("%s rejects with a clear ApiError when the body has no data field at all", async (_name, call) => {
    body = {};
    const error = await call().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: -1 });
  });

  it("createApiToken rejects a record without a token string instead of showing an empty token", async () => {
    body = successWith({ create_time: 1 });
    await expect(createApiToken()).rejects.toBeInstanceOf(ApiError);
  });

  it("still maps a well-formed body", async () => {
    body = successWith({ token: "tok-1", create_time: 5 });
    await expect(createApiToken()).resolves.toEqual({ token: "tok-1", createTime: 5 });
  });
});
