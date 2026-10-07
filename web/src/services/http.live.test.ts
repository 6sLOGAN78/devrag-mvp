import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { registerLiveAccount } from "@/test/live/account";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";
import { ApiError, request, requestWithMeta } from "./http";

// Runs against the real ingress (LIVE_BASE_URL, default http://127.0.0.1:8080). Needs the stack from plan 01-13.
describe("live http client", () => {
  let token = "";
  afterEach(() => removeAuthorization());

  it("waits for the ingress health route", async () => {
    await waitUntil(
      async () => {
        // Node's fetch has no base URL; resolve against the jsdom origin like the other live tests.
        const response = await fetch(new URL("/health", window.location.origin));
        return response.ok;
      },
      { describe: "GET /health on the ingress", timeout: 60_000 },
    );
  });

  it("registers a real account for the authenticated cases", async () => {
    token = await registerLiveAccount("http");
    expect(token.length).toBeGreaterThan(32);
  });

  it("an unknown path answers a real 401 envelope without a token (Python default deny)", async () => {
    const error = (await request({ url: "/api/v1/does-not-exist-unauth" }, { silent: true }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.code).toBe(401);
  });

  it("surfaces a real 404 envelope as ApiError plus a toast", async () => {
    setAuthorization(token);
    render(createElement(Toaster));
    const error = (await request({ url: "/api/v1/does-not-exist" }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe(404);
    expect(error.status).toBe(404);
    expect(await screen.findByText("Request failed")).toBeInTheDocument();
  });

  it("silent suppresses the toast", async () => {
    setAuthorization(token);
    render(createElement(Toaster));
    await request({ url: "/api/v1/does-not-exist-silent" }, { silent: true }).catch(() => undefined);
    expect(screen.queryByText("Request failed")).toBeNull();
  });

  it("sends the token to the real Python route and reads the source header", async () => {
    setAuthorization("live-test-token");
    const { source } = await requestWithMeta({ url: "/api/v1/system/healthz" }, { silent: true });
    expect(source).toBe("python");
  });
});
