import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";
import { ApiError, request, requestWithMeta } from "./http";

// Runs against the real ingress (LIVE_BASE_URL, default http://127.0.0.1:8080). Needs the stack from plan 01-13.
describe("live http client", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(
      async () => {
        const response = await fetch("/health");
        return response.ok;
      },
      { describe: "GET /health on the ingress", timeout: 60_000 },
    );
  });

  it("surfaces a real 404 envelope as ApiError plus a toast", async () => {
    render(createElement(Toaster));
    const error = (await request({ url: "/api/v1/does-not-exist" }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe(404);
    expect(error.status).toBe(404);
    expect(await screen.findByText("Request failed")).toBeInTheDocument();
  });

  it("silent suppresses the toast", async () => {
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
