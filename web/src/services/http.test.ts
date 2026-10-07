import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import type { AxiosAdapter, AxiosRequestConfig, AxiosResponse } from "axios";
import { AxiosError, AxiosHeaders } from "axios";
import { beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import i18n from "@/i18n";
import { useUserStore } from "@/stores/user-store";
import { getAuthorization, setAuthorization } from "@/utils/authorization";
import { ApiError, http, registerQueryClient, request, requestWithMeta } from "./http";

interface Reply {
  status?: number;
  data?: unknown;
  headers?: Record<string, string>;
  fail?: "network" | "timeout";
}

let seen: AxiosRequestConfig[] = [];
let reply: Reply = {};
let counter = 0;

const adapter: AxiosAdapter = (config) => {
  seen.push(config);
  const current = reply;
  if (current.fail) {
    return Promise.reject(
      new AxiosError(
        current.fail,
        current.fail === "timeout" ? "ECONNABORTED" : "ERR_NETWORK",
        config as never,
      ),
    );
  }
  const status = current.status ?? 200;
  const response: AxiosResponse = {
    data: current.data,
    status,
    statusText: String(status),
    headers: new AxiosHeaders(current.headers),
    config: config as never,
  };
  if (status >= 200 && status < 300) return Promise.resolve(response);
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config as never, null, response));
};

function uniqueMessage(base: string): string {
  counter += 1;
  return `${base} ${counter}`;
}

describe("unit http client", () => {
  beforeEach(() => {
    seen = [];
    reply = {};
    http.defaults.adapter = adapter;
  });

  it("unwraps a success envelope", async () => {
    reply = { data: { code: 0, message: "", data: { a: 1 } } };
    await expect(request<{ a: number }>({ url: "/x" })).resolves.toEqual({ a: 1 });
  });

  it("rejects ApiError on a non-zero code with HTTP 200 and toasts once", async () => {
    render(createElement(Toaster));
    const message = uniqueMessage("bad");
    reply = { data: { code: 101, message, data: null } };
    const error = await request({ url: "/x" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: 101, status: 200, message });
    expect(await screen.findByText(i18n.t("toast.apiError.title"))).toBeInTheDocument();
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(await screen.findByText("Code 101")).toBeInTheDocument();
  });

  it("rejects ApiError on a 4xx envelope and keeps data", async () => {
    reply = { status: 404, data: { code: 404, message: "missing", data: { why: "x" } } };
    const error = (await request({ url: "/x" }, { silent: true }).catch((e: unknown) => e)) as ApiError;
    expect(error).toMatchObject({ code: 404, status: 404, message: "missing", data: { why: "x" } });
  });

  it("silent suppresses the toast", async () => {
    render(createElement(Toaster));
    const message = uniqueMessage("quiet");
    reply = { data: { code: 101, message, data: null } };
    await request({ url: "/x" }, { silent: true }).catch(() => undefined);
    await request({ url: "/x" }).catch(() => undefined);
    // The non-silent call proves the toaster works; the silent one must not have added a second toast.
    expect(await screen.findAllByText(message)).toHaveLength(1);
  });

  it("falls back when the server message is empty or longer than 160 characters", async () => {
    render(createElement(Toaster));
    reply = { data: { code: 101, message: "x".repeat(161), data: null } };
    await request({ url: "/x" }).catch(() => undefined);
    expect(await screen.findByText(i18n.t("toast.apiError.fallback"))).toBeInTheDocument();
    expect(screen.queryByText("x".repeat(161))).toBeNull();
  });

  it("dedupes identical failures", async () => {
    render(createElement(Toaster));
    const message = uniqueMessage("same");
    reply = { data: { code: 101, message, data: null } };
    await request({ url: "/x" }).catch(() => undefined);
    await request({ url: "/x" }).catch(() => undefined);
    expect(await screen.findAllByText(message)).toHaveLength(1);
  });

  it("on 401 purges token, user store and query cache and toasts once", async () => {
    render(createElement(Toaster));
    const qc = new QueryClient();
    qc.setQueryData(["k"], 1);
    registerQueryClient(qc);
    setAuthorization("tok");
    useUserStore.getState().setUserId("u1");
    reply = { status: 401, data: { code: 401, message: "no", data: null } };
    await request({ url: "/x" }).catch(() => undefined);
    await request({ url: "/x" }).catch(() => undefined);
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().userId).toBeNull();
    expect(qc.getQueryData(["k"])).toBeUndefined();
    expect(await screen.findAllByText(i18n.t("toast.session.description"))).toHaveLength(1);
    expect(screen.getByText("Your session ended. Reload the page to continue.")).toBeInTheDocument();
  });

  it("maps a 5xx without an envelope to code -1 and the server error copy", async () => {
    render(createElement(Toaster));
    reply = { status: 502, data: "<html>bad gateway</html>" };
    const error = (await request({ url: "/x" }).catch((e: unknown) => e)) as ApiError;
    expect(error).toMatchObject({ code: -1, status: 502 });
    expect(await screen.findByText(i18n.t("toast.serverError.title"))).toBeInTheDocument();
    expect(screen.queryByText(/bad gateway/)).toBeNull();
  });

  it("maps a network failure to status 0", async () => {
    render(createElement(Toaster));
    reply = { fail: "network" };
    const error = (await request({ url: "/x" }).catch((e: unknown) => e)) as ApiError;
    expect(error).toMatchObject({ status: 0 });
    expect(await screen.findByText(i18n.t("toast.network.title"))).toBeInTheDocument();
  });

  it("maps a timeout to the timeout copy and uses a 10 s default", async () => {
    render(createElement(Toaster));
    expect(http.defaults.timeout).toBe(10_000);
    reply = { fail: "timeout" };
    const error = (await request({ url: "/x" }).catch((e: unknown) => e)) as ApiError;
    expect(error).toMatchObject({ status: 0 });
    expect(await screen.findByText(i18n.t("toast.timeout.title"))).toBeInTheDocument();
  });

  it("injects the bearer header only when a token exists", async () => {
    reply = { data: { code: 0, message: "", data: null } };
    await request({ url: "/x" });
    expect(new AxiosHeaders(seen[0].headers as never).get("Authorization")).toBeUndefined();
    setAuthorization("tok");
    await request({ url: "/x" });
    expect(new AxiosHeaders(seen[1].headers as never).get("Authorization")).toBe("Bearer tok");
  });

  it("requestWithMeta returns the x-api-source header", async () => {
    reply = { data: { code: 0, message: "", data: { ok: true } }, headers: { "x-api-source": "python" } };
    await expect(requestWithMeta({ url: "/x" })).resolves.toEqual({ data: { ok: true }, source: "python" });
  });

  it("returns a non-envelope 2xx body as is", async () => {
    reply = { data: { status: "ok" } };
    await expect(request({ url: "/x" })).resolves.toEqual({ status: "ok" });
  });
});

function authOf(index: number): unknown {
  return new AxiosHeaders(seen[index].headers as never).get("Authorization");
}

describe("unit http client token handling", () => {
  beforeEach(() => {
    seen = [];
    reply = {};
    localStorage.clear();
    useUserStore.getState().reset();
    http.defaults.adapter = adapter;
  });

  it("attaches the token to a relative URL", async () => {
    setAuthorization("fake-token-aaa");
    reply = { data: { code: 0, message: "", data: null } };
    await request({ url: "/api/v1/x" });
    expect(authOf(0)).toBe("Bearer fake-token-aaa");
  });

  it("attaches the token to an absolute URL on the page origin", async () => {
    setAuthorization("fake-token-aaa");
    reply = { data: { code: 0, message: "", data: null } };
    await request({ url: `${window.location.origin}/api/v1/x` });
    expect(authOf(0)).toBe("Bearer fake-token-aaa");
  });

  it("never attaches the token to another origin", async () => {
    setAuthorization("fake-token-aaa");
    reply = { data: { code: 0, message: "", data: null } };
    await request({ url: "https://files.example.test/avatar.png" });
    expect(authOf(0)).toBeUndefined();
  });

  it("never attaches the token to a protocol-relative URL", async () => {
    setAuthorization("fake-token-aaa");
    reply = { data: { code: 0, message: "", data: null } };
    await request({ url: "//evil.example.test/x" });
    expect(authOf(0)).toBeUndefined();
  });

  it.each([
    ["HTTP 401", { status: 401 }],
    ["envelope 401 with HTTP 200", { status: 200 }],
  ])("keeps state and shows the server message on a tokenless 401 (%s)", async (_name, extra) => {
    render(createElement(Toaster));
    const qc = new QueryClient();
    qc.setQueryData(["k"], 1);
    registerQueryClient(qc);
    useUserStore.getState().setUserId("u1");
    const message = uniqueMessage("wrong credentials");
    reply = { ...extra, data: { code: 401, message, data: null } };
    const error = await request({ url: "/x" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: 401, message });
    expect(useUserStore.getState().userId).toBe("u1");
    expect(qc.getQueryData(["k"])).toBe(1);
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByText(i18n.t("toast.session.description"))).toBeNull();
  });

  it.each([
    ["HTTP 401", 401],
    ["envelope 401 with HTTP 200", 200],
  ])("purges when the sent token is still current (%s)", async (_name, status) => {
    const qc = new QueryClient();
    qc.setQueryData(["k"], 1);
    registerQueryClient(qc);
    setAuthorization("fake-token-aaa");
    useUserStore.getState().setUserId("u1");
    reply = { status, data: { code: 401, message: "expired", data: null } };
    await request({ url: "/x" }).catch(() => undefined);
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().userId).toBeNull();
    expect(qc.getQueryData(["k"])).toBeUndefined();
  });

  it.each([
    ["HTTP 401", 401],
    ["envelope 401 with HTTP 200", 200],
  ])("does not purge a newer login on a late 401 (%s)", async (_name, status) => {
    const qc = new QueryClient();
    qc.setQueryData(["k"], 1);
    registerQueryClient(qc);
    setAuthorization("fake-token-aaa");
    useUserStore.getState().setUserId("u1");
    const late: AxiosAdapter = (config) => {
      setAuthorization("fake-token-bbb");
      return adapter(config);
    };
    reply = { status, data: { code: 401, message: "stale", data: null } };
    await request({ url: "/x", adapter: late }, { silent: true }).catch(() => undefined);
    expect(getAuthorization()).toBe("fake-token-bbb");
    expect(useUserStore.getState().userId).toBe("u1");
    expect(qc.getQueryData(["k"])).toBe(1);
  });

  it("shows no toast for a silent tokenless 401", async () => {
    render(createElement(Toaster));
    const message = uniqueMessage("silent wrong credentials");
    reply = { status: 401, data: { code: 401, message, data: null } };
    await request({ url: "/x" }, { silent: true }).catch(() => undefined);
    await request({ url: "/x" }).catch(() => undefined);
    expect(await screen.findAllByText(message)).toHaveLength(1);
  });
});
