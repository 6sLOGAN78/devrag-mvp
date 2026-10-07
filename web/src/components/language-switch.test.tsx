import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { LanguageSwitch } from "@/components/language-switch";
import i18n from "@/i18n";
import { LANG_KEY } from "@/i18n/language";
import { BareLayout } from "@/layouts/bare-layout";
import { waitUntil } from "@/test/wait-until";

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

describe("LanguageSwitch", () => {
  it("is a labelled icon button that opens English and 中文, each in its own language", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitch />);
    const trigger = screen.getByTestId("language-switch");
    expect(trigger).toBe(screen.getByRole("button", { name: "Change language" }));
    await user.click(trigger);
    const en = await screen.findByTestId("language-option-en");
    const zh = screen.getByTestId("language-option-zh");
    expect(en).toHaveTextContent("English");
    expect(zh).toHaveTextContent("中文");
    expect(en).toHaveAttribute("lang", "en");
    expect(zh).toHaveAttribute("lang", "zh");
    expect(within(en).getByTestId("language-current")).toBeInTheDocument();
    expect(within(zh).queryByTestId("language-current")).toBeNull();
  });

  it("applies the choice at once, sets <html lang>, persists it and shows no toast", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitch />);
    await user.click(screen.getByTestId("language-switch"));
    await user.click(await screen.findByTestId("language-option-zh"));
    await waitUntil(() => i18n.language === "zh", { describe: "language zh" });
    expect(document.documentElement.lang).toBe("zh");
    expect(localStorage.getItem(LANG_KEY)).toBe("zh");
    expect(screen.getByTestId("language-switch")).toHaveAttribute("aria-label", "切换语言");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });
});

describe("BareLayout corner cluster", () => {
  it("lets a signed-out visitor change language and theme", () => {
    const router = createMemoryRouter([{ element: <BareLayout />, children: [{ path: "*", element: <p>page body</p> }] }]);
    render(<RouterProvider router={router} />);
    expect(screen.getByTestId("language-switch")).toBeInTheDocument();
    expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  it("stays blank when a guard supplies its own children", () => {
    render(<BareLayout>{null}</BareLayout>);
    expect(screen.queryByTestId("language-switch")).toBeNull();
  });
});
