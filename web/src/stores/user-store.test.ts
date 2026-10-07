import { beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { useUserStore } from "./user-store";

const user: SessionUser = {
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

describe("user store", () => {
  beforeEach(() => useUserStore.getState().reset());

  it("starts signed out", () => {
    expect(useUserStore.getState()).toMatchObject({ user: null, userId: null });
  });

  it("setUser stores the typed user and mirrors its id", () => {
    useUserStore.getState().setUser(user);
    expect(useUserStore.getState().user).toEqual(user);
    expect(useUserStore.getState().userId).toBe("u1");
  });

  it("clearUser and reset both drop the user and the id", () => {
    useUserStore.getState().setUser(user);
    useUserStore.getState().clearUser();
    expect(useUserStore.getState()).toMatchObject({ user: null, userId: null });
    useUserStore.getState().setUser(user);
    useUserStore.getState().reset();
    expect(useUserStore.getState()).toMatchObject({ user: null, userId: null });
  });

  it("keeps the legacy setUserId setter", () => {
    useUserStore.getState().setUserId("u9");
    expect(useUserStore.getState().userId).toBe("u9");
  });
});
