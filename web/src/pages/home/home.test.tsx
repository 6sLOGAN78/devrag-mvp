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
    // Only the profile row exists now; the tokens and team rows arrive with their own pages.
    const links = screen.queryAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/user-setting/profile"]);
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("has a Manage your account card with an Edit your profile link row to the profile page", () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const card = screen.getByTestId("home-links");
    expect(within(card).getByRole("heading", { level: 2, name: "Manage your account" })).toBeInTheDocument();
    const link = within(card).getByRole("link", { name: "Edit your profile" });
    expect(link).toHaveAttribute("href", "/user-setting/profile");
    expect(link.querySelector("svg")).not.toBeNull();
  });

  it("does not render the account links while the user is loading", () => {
    renderHome();
    expect(screen.queryByTestId("home-links")).toBeNull();
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
