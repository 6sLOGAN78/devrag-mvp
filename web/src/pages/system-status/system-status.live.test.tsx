import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { waitUntil } from "@/test/wait-until";
import SystemStatusPage from "./index";

// Runs against the real ingress (LIVE_BASE_URL). Needs the full stack up and healthy.
describe("live System status page", () => {
  it("shows both engines healthy from the real routes", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, {
      describe: "ingress /health",
      timeout: 60_000,
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SystemStatusPage />
      </QueryClientProvider>,
    );
    const goCard = screen.getByTestId("status-card-go");
    const pyCard = screen.getByTestId("status-card-python");
    await waitUntil(
      () =>
        within(goCard).queryByTestId("status-card-go-badge") !== null &&
        within(pyCard).queryByTestId("status-card-python-badge") !== null,
      { describe: "both cards leave loading", timeout: 30_000 },
    );
    expect(within(goCard).getByTestId("status-card-go-badge")).toHaveTextContent("Healthy");
    expect(within(goCard).getByTestId("status-card-go-source")).toHaveTextContent("go");
    expect(within(pyCard).getByTestId("status-card-python-badge")).toHaveTextContent("Healthy");
    expect(within(pyCard).getByTestId("status-card-python-source")).toHaveTextContent("python");
    for (const name of ["database", "redis", "storage", "doc_store"]) {
      expect(within(pyCard).getByTestId(`status-dependency-${name}`)).toHaveTextContent("OK");
    }
  });
});
