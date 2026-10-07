import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { act } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { SkipLink } from "@/components/skip-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { TooltipProvider } from "@/components/ui/tooltip";
import { navEntries } from "@/constants/routes";
import i18n, { setLanguage } from "@/i18n";
import zh from "@/locales/zh.json";

describe("shared shell follows the language (UI-42)", () => {
  it("renders English by default through the real i18n instance", () => {
    render(<ErrorState noun="service status" onAction={() => {}} code={500} />);
    expect(screen.getByRole("heading", { name: "Couldn't load service status" })).toBeInTheDocument();
    expect(screen.getByText("Code 500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders Chinese after setLanguage, persists it and sets html lang", async () => {
    await act(async () => {
      await setLanguage("zh");
    });
    render(<ErrorState onAction={() => {}} />);
    expect(screen.getByRole("heading", { name: i18n.t("errorState.headingFor", { noun: zh.errorState.defaultNoun }) })).toBeInTheDocument();
    expect(screen.getByRole("heading").textContent).toBe("无法加载数据");
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(localStorage.getItem("devrag.lang")).toBe("zh");
    expect(document.documentElement.lang).toBe("zh");
  });

  it("empty state, skip link and theme toggle translate", async () => {
    await act(async () => {
      await setLanguage("zh");
    });
    render(
      <>
        <SkipLink />
        <ThemeToggle />
        <EmptyState noun="知识库" />
      </>,
    );
    expect(screen.getByText("跳到主要内容")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "切换主题" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "还没有知识库" })).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("theme-toggle"));
    expect(await screen.findByText("深色")).toBeInTheDocument();
  });

  it("route registry stores label keys and the sidebar resolves them per language", async () => {
    expect(navEntries().map((entry) => entry.nav?.labelKey)).toEqual(["nav.home", "nav.systemStatus", "nav.profile", "nav.apiTokens"]);
    await act(async () => {
      await setLanguage("zh");
    });
    render(
      <MemoryRouter>
        <TooltipProvider>
          <AppSidebar forceLabels />
        </TooltipProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByText("首页")).toBeInTheDocument();
    expect(screen.getByText("系统状态")).toBeInTheDocument();
  });
});
