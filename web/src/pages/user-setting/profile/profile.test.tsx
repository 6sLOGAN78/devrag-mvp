import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import i18n, { setLanguage } from "@/i18n";
import type { SessionUser } from "@/interfaces/user";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";
import { AvatarError } from "./avatar";
import ProfilePage from ".";

vi.mock("./avatar", async (importOriginal) => {
  const original = await importOriginal<typeof import("./avatar")>();
  return { ...original, downscaleToDataUrl: vi.fn() };
});
const avatarModule = await import("./avatar");
const downscale = vi.mocked(avatarModule.downscaleToDataUrl);

const originalAdapter = http.defaults.adapter;
const PNG = "data:image/png;base64,iVBORw0KGgo=";
const NEW_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==";

const USER: SessionUser = {
  id: "u1",
  nickname: "Ada Lovelace",
  email: "ada@example.test",
  avatar: "",
  language: "en",
  colorSchema: "Bright",
  tenantId: "t1",
  tenantName: "Ada's workspace",
  role: "owner",
  isSuperuser: false,
};

type Responder = (config: InternalAxiosRequestConfig) => Promise<unknown> | unknown;
let calls: InternalAxiosRequestConfig[] = [];
let responder: Responder;

const ok = (config: InternalAxiosRequestConfig, data: unknown = null) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, status: number, code: number, message: string) {
  const response = { data: { code, message, data: null }, status, statusText: String(status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  return Promise.resolve(responder(config)) as never;
};

const settingCalls = () => calls.filter((c) => c.url === "/v1/user/setting");
const bodyOf = (config: InternalAxiosRequestConfig) => JSON.parse(String(config.data)) as Record<string, unknown>;

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ProfilePage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

const save = () => screen.getByRole("button", { name: "Save profile" });
const nickname = () => screen.getByLabelText("Nickname");

beforeEach(() => {
  calls = [];
  responder = (config) => ok(config, { id: "u1" });
  downscale.mockReset();
  useUserStore.getState().setUser(USER);
  setAuthorization("tok-a");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

describe("profile page (UI-34)", () => {
  it("has the page heading as the first heading, the test ids and the document title", () => {
    renderPage();
    const page = screen.getByTestId("profile-page");
    const headings = within(page).getAllByRole("heading");
    expect(within(page).getByRole("heading", { level: 1, name: "Profile" })).toBe(headings[0]);
    expect(within(page).getByRole("heading", { level: 2, name: "Your profile" })).toBeInTheDocument();
    expect(screen.getByTestId("profile-form")).toBeInTheDocument();
    expect(document.title).toBe("Profile - devRag");
  });

  it("shows the email read-only as a focusable field with its explanation and never sends it", async () => {
    renderPage();
    const email = screen.getByLabelText("Email");
    expect(email).toHaveValue("ada@example.test");
    expect(email).toHaveAttribute("readonly");
    expect(email).toHaveAttribute("aria-readonly", "true");
    expect(email).toHaveAttribute("aria-describedby");
    expect(screen.getByText("Your email can't be changed.")).toHaveAttribute("id", email.getAttribute("aria-describedby")!);
    email.focus();
    expect(email).toHaveFocus();
    await userEvent.type(nickname(), "x");
    await userEvent.click(save());
    await waitUntil(() => settingCalls().length === 1, { describe: "profile save request" });
    expect(String(settingCalls()[0]!.data)).not.toContain("ada@example.test");
  });

  it("keeps Save profile aria-disabled until the form is dirty and valid, and ignores clicks while it is", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(save()).toHaveAttribute("aria-disabled", "true");
    await user.click(save());
    expect(calls).toHaveLength(0);

    await user.type(nickname(), "!");
    expect(save()).not.toHaveAttribute("aria-disabled");

    await user.clear(nickname());
    expect(save()).toHaveAttribute("aria-disabled", "true");
    expect(nickname()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Enter a nickname.").closest("[role=alert]")).not.toBeNull();
    await user.click(save());
    expect(calls).toHaveLength(0);

    await user.type(nickname(), "Ada Lovelace  ");
    expect(save()).toHaveAttribute("aria-disabled", "true");
  });

  it.each([
    ["a nickname over 64 characters", "x".repeat(65), "Use 64 characters or fewer."],
    ["angle brackets", "<b>Ada</b>", "This nickname contains characters that are not allowed."],
  ])("refuses %s on the client and sends nothing", async (_name, value, message) => {
    const user = userEvent.setup();
    renderPage();
    await user.clear(nickname());
    await user.click(nickname());
    await user.paste(value);
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(save()).toHaveAttribute("aria-disabled", "true");
    await user.click(save());
    expect(calls).toHaveLength(0);
  });

  it("saves only the edited nickname, updates the store and the cached user without a reload and toasts", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.clear(nickname());
    await user.type(nickname(), "  Grace Hopper ");
    await user.click(save());
    expect(await screen.findByText("Profile saved")).toBeInTheDocument();
    expect(settingCalls()).toHaveLength(1);
    const request = settingCalls()[0]!;
    expect(request.method).toBe("post");
    expect(bodyOf(request)).toEqual({ nickname: "Grace Hopper" });
    expect(new AxiosHeaders(request.headers as never).get("Authorization")).toBe("Bearer tok-a");
    expect(useUserStore.getState().user?.nickname).toBe("Grace Hopper");
    expect(useUserStore.getState().user?.email).toBe("ada@example.test");
    expect(useUserStore.getState().user?.id).toBe("u1");
    // The form is clean again after saving.
    expect(save()).toHaveAttribute("aria-disabled", "true");
    expect(nickname()).toHaveValue("Grace Hopper");
  });

  it("never sends identity, tenant, role, e-mail or token fields", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(nickname(), "2");
    await user.click(save());
    await waitUntil(() => settingCalls().length === 1, { describe: "profile save request" });
    const keys = Object.keys(bodyOf(settingCalls()[0]!));
    expect(keys.every((key) => ["nickname", "avatar", "language", "color_schema"].includes(key))).toBe(true);
    expect(String(settingCalls()[0]!.data)).not.toMatch(/tenant|role|email|token|"id"|superuser/i);
  });

  it("prevents a double submit while the request is pending", async () => {
    let release: (value: unknown) => void = () => undefined;
    responder = (config) => new Promise((resolve) => (release = () => resolve(ok(config, { id: "u1" }))));
    const user = userEvent.setup();
    renderPage();
    await user.type(nickname(), "2");
    await user.click(save());
    await waitUntil(() => settingCalls().length === 1, { describe: "first request" });
    expect(save()).toHaveAttribute("aria-disabled", "true");
    expect(save()).toHaveAttribute("aria-busy", "true");
    await user.click(save());
    await user.keyboard("{Enter}");
    expect(settingCalls()).toHaveLength(1);
    await act(async () => release(null));
    expect(await screen.findByText("Profile saved")).toBeInTheDocument();
    expect(settingCalls()).toHaveLength(1);
  });

  it("shows a failed save in the form alert, shows no request-error toast and keeps the edit", async () => {
    responder = (config) => failure(config, 400, 101, "nickname contains characters that are not allowed");
    const user = userEvent.setup();
    renderPage();
    await user.type(nickname(), "2");
    await user.click(save());
    const alert = await screen.findByTestId("alert-form-error");
    expect(alert).toHaveTextContent("nickname contains characters that are not allowed");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(nickname()).toHaveValue("Ada Lovelace2");
    expect(useUserStore.getState().user?.nickname).toBe("Ada Lovelace");
    expect(save()).not.toHaveAttribute("aria-disabled");
  });

  it("uses the generic message when the server message is empty or long, and for an outage", async () => {
    responder = (config) => failure(config, 500, -1, "x".repeat(400));
    const user = userEvent.setup();
    renderPage();
    await user.type(nickname(), "2");
    await user.click(save());
    expect(await screen.findByTestId("alert-form-error")).toHaveTextContent("Something went wrong. Try again.");
  });

  it("renders a hostile nickname as text and never as markup", () => {
    useUserStore.getState().setUser({ ...USER, nickname: '<img src=x onerror="alert(1)">', email: "a@example.test" });
    renderPage();
    expect(screen.getByTestId("profile-page").querySelector("img")).toBeNull();
    expect(nickname()).toHaveValue('<img src=x onerror="alert(1)">');
  });

  it("follows the language switch", async () => {
    renderPage();
    await act(async () => {
      await setLanguage("zh");
    });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(i18n.t("profile.title"));
    expect(screen.getByRole("heading", { level: 1 }).textContent).not.toBe("Profile");
    expect(document.title).toBe(i18n.t("profile.pageTitle"));
  });
});

describe("profile avatar (T-02-71, T-02-74)", () => {
  const upload = (file = new File([new Uint8Array([1, 2, 3])], "me.png", { type: "image/png" })) => userEvent.upload(screen.getByTestId("avatar-input"), file);

  it("has a native file input limited to PNG, JPEG and WebP with an accessible name, and a keyboard-operable button", async () => {
    renderPage();
    const input = screen.getByTestId("avatar-input");
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("accept", "image/png,image/jpeg,image/webp");
    expect(input).toHaveAccessibleName("Change avatar");
    const button = screen.getByRole("button", { name: "Change avatar" });
    const clicked = vi.spyOn(input, "click");
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(clicked).toHaveBeenCalled();
    expect(screen.getByText("PNG, JPEG or WebP. Resized to 256 by 256 pixels, up to 256 KB.")).toBeInTheDocument();
  });

  it("shows Remove avatar only when an avatar exists", async () => {
    renderPage();
    expect(screen.queryByTestId("avatar-remove")).toBeNull();
    downscale.mockResolvedValue(NEW_PNG);
    await upload();
    expect(await screen.findByTestId("avatar-remove")).toHaveTextContent("Remove avatar");
  });

  it("previews the staged avatar at once, but only the app-produced data URL, and saves it with the form", async () => {
    downscale.mockResolvedValue(NEW_PNG);
    renderPage();
    await upload();
    await waitUntil(() => screen.getByTestId("profile-page").querySelector("img") !== null, { describe: "avatar preview" });
    expect(screen.getByTestId("profile-page").querySelector("img")).toHaveAttribute("src", NEW_PNG);
    expect(calls).toHaveLength(0);
    expect(save()).not.toHaveAttribute("aria-disabled");
    await userEvent.click(save());
    expect(await screen.findByText("Profile saved")).toBeInTheDocument();
    expect(bodyOf(settingCalls()[0]!)).toEqual({ avatar: NEW_PNG });
    expect(useUserStore.getState().user?.avatar).toBe(NEW_PNG);
    expect(save()).toHaveAttribute("aria-disabled", "true");
  });

  it("sends nickname and avatar together when both changed", async () => {
    downscale.mockResolvedValue(NEW_PNG);
    const user = userEvent.setup();
    renderPage();
    await user.type(nickname(), "2");
    await upload();
    await user.click(save());
    await screen.findByText("Profile saved");
    expect(bodyOf(settingCalls()[0]!)).toEqual({ nickname: "Ada Lovelace2", avatar: NEW_PNG });
  });

  it("removes the avatar by sending an empty string", async () => {
    useUserStore.getState().setUser({ ...USER, avatar: PNG });
    renderPage();
    expect(screen.getByTestId("profile-page").querySelector("img")).toHaveAttribute("src", PNG);
    await userEvent.click(screen.getByTestId("avatar-remove"));
    expect(screen.getByTestId("profile-page").querySelector("img")).toBeNull();
    expect(screen.queryByTestId("avatar-remove")).toBeNull();
    await userEvent.click(save());
    await screen.findByText("Profile saved");
    expect(bodyOf(settingCalls()[0]!)).toEqual({ avatar: "" });
    expect(useUserStore.getState().user?.avatar).toBe("");
  });

  it("explains a 413 on avatar save in a translated sentence, whatever the proxy body says, and keeps the staged image (R-130)", async () => {
    downscale.mockResolvedValue(NEW_PNG);
    responder = (config) => failure(config, 413, 400, "Request Entity Too Large");
    renderPage();
    await upload();
    await userEvent.click(save());
    expect(await screen.findByTestId("alert-form-error")).toHaveTextContent("That upload is too large to save. Choose a smaller image and try again.");
    expect(screen.queryByText("Request Entity Too Large")).toBeNull();
    expect(screen.getByTestId("profile-page").querySelector("img")).toHaveAttribute("src", NEW_PNG);
    expect(useUserStore.getState().user?.avatar).toBe("");
  });

  it("falls back to initials when the stored avatar is not a safe data URL", () => {
    useUserStore.getState().setUser({ ...USER, avatar: "https://evil.example/a.png" });
    renderPage();
    const page = screen.getByTestId("profile-page");
    expect(page.querySelector("img")).toBeNull();
    expect(within(page).getByTestId("avatar-initials")).toHaveTextContent("AL");
  });

  it.each([
    ["errors.avatar.type", "Choose a PNG, JPEG or WebP image."],
    ["errors.avatar.decode", "That file couldn't be read as an image. Choose a different PNG, JPEG or WebP file."],
    ["errors.avatar.size", "That image is still over 256 KB after resizing. Choose a smaller one."],
  ] as const)("shows the %s message inline under the avatar row, keeps the old avatar and stages nothing", async (key, message) => {
    downscale.mockRejectedValue(new AvatarError(key));
    renderPage();
    await upload();
    const alert = (await screen.findByText(message)).closest("[role=alert]");
    expect(alert).not.toBeNull();
    expect(screen.getByRole("button", { name: "Change avatar" })).toHaveAttribute("aria-describedby", alert!.getAttribute("id"));
    expect(save()).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("profile-page").querySelector("img")).toBeNull();
  });

  it("clears the inline error once a good image is chosen", async () => {
    downscale.mockRejectedValueOnce(new AvatarError("errors.avatar.type")).mockResolvedValueOnce(NEW_PNG);
    renderPage();
    await upload();
    await screen.findByText("Choose a PNG, JPEG or WebP image.");
    await upload(new File([new Uint8Array([4, 5, 6])], "ok.png", { type: "image/png" }));
    await waitUntil(() => screen.queryByText("Choose a PNG, JPEG or WebP image.") === null, { describe: "error cleared" });
  });

  it("treats an unexpected failure from the helper as an unreadable image", async () => {
    downscale.mockRejectedValue(new Error("boom"));
    renderPage();
    await upload();
    expect(await screen.findByText(/couldn't be read as an image/)).toBeInTheDocument();
  });
});
