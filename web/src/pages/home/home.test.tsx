import { render, screen, within } from "@testing-library/react";
import { act } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import i18n, { setLanguage } from "@/i18n";
import type { SessionUser } from "@/interfaces/user";
import { useUserStore } from "@/stores/user-store";
import HomePage from ".";

const USER: SessionUser = {
  id: "u1",
  nickname: "Ada",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  colorSchema: "Bright",
  tenantId: "t1",
  tenantName: "Ada's workspace",
  role: "owner",
  isSuperuser: false,
};

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );
}

beforeEach(() => useUserStore.getState().reset());
afterEach(() => useUserStore.getState().reset());

describe("home dashboard (UI-09)", () => {
  it("makes the page title the first read element and shows the workspace line from the user's real data", () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const page = screen.getByTestId("home-page");
    const title = within(page).getByRole("heading", { level: 1 });
    expect(title).toHaveTextContent("Welcome, Ada");
    expect(page.firstElementChild?.contains(title)).toBe(true);
    expect(within(page).getByText("Workspace: Ada's workspace")).toBeInTheDocument();
    expect(document.title).toBe("Home - devRag");
  });

  it.each([
    ["owner", "Owner"],
    ["admin", "Admin"],
    ["normal", "Member"],
    ["member", "Member"],
  ])("shows the %s role as %s in the role card", (role, label) => {
    useUserStore.getState().setUser({ ...USER, role });
    renderHome();
    const card = screen.getByTestId("stat-role");
    expect(card).toHaveTextContent("Your role");
    expect(card).toHaveTextContent(label);
  });

  it("shows loading skeletons and no title until the user is known", () => {
    renderHome();
    expect(screen.getByTestId("home-skeleton")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /Welcome/ })).toBeNull();
    expect(screen.queryByTestId("stat-role")).toBeNull();
  });

  it("renders no placeholder tiles and no dead links for data that does not exist yet", () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    for (const id of ["stat-members", "stat-tokens", "stat-invitations"]) expect(screen.queryByTestId(id)).toBeNull();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("renders text only: a hostile nickname is never interpreted as markup", () => {
    useUserStore.getState().setUser({ ...USER, nickname: "<img src=x onerror=alert(1)>" });
    renderHome();
    expect(screen.getByTestId("home-page").querySelector("img")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome, <img src=x onerror=alert(1)>");
  });

  it("follows the language switch", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome, Ada");
    await act(async () => {
      await setLanguage("zh");
    });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(i18n.t("home.title", { nickname: "Ada" }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).not.toContain("Welcome");
  });
});
