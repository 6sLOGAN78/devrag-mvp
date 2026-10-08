import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Membership } from "@/services/team-service";
import { buildWorkspaceList, useWorkspaceStore, WORKSPACE_STORAGE_KEY } from "./workspace-store";

const membership = (tenantId: string, tenantName: string, role: string, ownerNickname = "Grace"): Membership => ({
  tenantId,
  tenantName,
  ownerNickname,
  ownerAvatar: "",
  role,
  joinedTime: "2026-10-01T12:00:00Z",
});

const OWN = membership("t1", "Ada's workspace", "owner", "Ada");
const ADMIN_IN = membership("t9", "Grace's workspace", "admin");
const NORMAL_IN = membership("t7", "Alan's workspace", "normal", "Alan");
const INVITED = membership("t8", "Hal's workspace", "invite", "Hal");

function stored(): unknown {
  const raw = localStorage.getItem(WORKSPACE_STORAGE_KEY);
  return raw === null ? null : JSON.parse(raw);
}

describe("workspace store", () => {
  beforeEach(() => useWorkspaceStore.getState().reset());
  afterEach(() => vi.restoreAllMocks());

  it("persists under devrag.workspace", () => {
    expect(WORKSPACE_STORAGE_KEY).toBe("devrag.workspace");
  });

  it("has no active workspace until it is initialised", () => {
    expect(useWorkspaceStore.getState().activeTenantId).toBeNull();
  });

  it("selects the own workspace when nothing is stored", () => {
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
  });

  it("restores the stored workspace for the same user when it is still in the list", () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ userId: "u1", tenantId: "t9" }));
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
  });

  it("ignores a stored workspace that is not in the server list (forged or stale value)", () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ userId: "u1", tenantId: "t666" }));
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
  });

  it("does not accept a pending invitation as a workspace", () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ userId: "u1", tenantId: "t8" }));
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, INVITED]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
  });

  it("ignores, and does not delete, a stored entry that belongs to another user", () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ userId: "someone-else", tenantId: "t9" }));
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
    expect(stored()).toEqual({ userId: "someone-else", tenantId: "t9" });
  });

  it("ignores malformed stored values", () => {
    for (const raw of ["not json", "null", "[]", JSON.stringify({ userId: 1, tenantId: 2 }), JSON.stringify({ userId: "u1" })]) {
      localStorage.setItem(WORKSPACE_STORAGE_KEY, raw);
      useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
      expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
    }
  });

  it("setActive stores {userId, tenantId} and accepts only the own or a joined workspace", () => {
    const store = useWorkspaceStore.getState();
    store.initialise("u1", "t1", [OWN, ADMIN_IN, INVITED]);
    store.setActive("t9");
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
    expect(stored()).toEqual({ userId: "u1", tenantId: "t9" });
    store.setActive("t8");
    store.setActive("t666");
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
    store.setActive("t1");
    expect(stored()).toEqual({ userId: "u1", tenantId: "t1" });
  });

  it("falls back to the own workspace and reports the lost workspace name once when it leaves the list", () => {
    const store = useWorkspaceStore.getState();
    store.initialise("u1", "t1", [OWN, ADMIN_IN]);
    store.setActive("t9");
    store.setMemberships([OWN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
    expect(useWorkspaceStore.getState().lost).toBe("Grace's workspace");
    expect(stored()).toEqual({ userId: "u1", tenantId: "t1" });
    useWorkspaceStore.getState().clearLost();
    expect(useWorkspaceStore.getState().lost).toBeNull();
    useWorkspaceStore.getState().setMemberships([OWN]);
    expect(useWorkspaceStore.getState().lost).toBeNull();
  });

  it("keeps the active workspace and reports nothing when it is still listed", () => {
    const store = useWorkspaceStore.getState();
    store.initialise("u1", "t1", [OWN, ADMIN_IN]);
    store.setActive("t9");
    store.setMemberships([OWN, ADMIN_IN, NORMAL_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
    expect(useWorkspaceStore.getState().lost).toBeNull();
  });

  it("reset clears the state and the stored entry", () => {
    const store = useWorkspaceStore.getState();
    store.initialise("u1", "t1", [OWN, ADMIN_IN]);
    store.setActive("t9");
    store.reset();
    expect(useWorkspaceStore.getState().activeTenantId).toBeNull();
    expect(useWorkspaceStore.getState().memberships).toEqual([]);
    expect(stored()).toBeNull();
  });

  it("works from memory when localStorage throws on every read and write", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const store = useWorkspaceStore.getState();
    expect(() => store.initialise("u1", "t1", [OWN, ADMIN_IN])).not.toThrow();
    expect(() => store.setActive("t9")).not.toThrow();
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
    // A later initialise in the same tab still finds the choice in memory.
    useWorkspaceStore.setState({ activeTenantId: null, initialisedFor: null });
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
    expect(() => useWorkspaceStore.getState().reset()).not.toThrow();
    expect(useWorkspaceStore.getState().activeTenantId).toBeNull();
    useWorkspaceStore.getState().initialise("u1", "t1", [OWN, ADMIN_IN]);
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
  });
});

describe("buildWorkspaceList", () => {
  const own = { tenantId: "t1", name: "Ada's workspace", ownerNickname: "Ada" };

  it("lists the own workspace first, then admin and normal rows by name, and drops invitations", () => {
    const list = buildWorkspaceList(own, [INVITED, NORMAL_IN, OWN, ADMIN_IN, membership("t5", "Zed's workspace", "normal", "Zed")], "en");
    expect(list.map((w) => w.tenantId)).toEqual(["t1", "t7", "t9", "t5"]);
    expect(list[0]).toMatchObject({ role: "owner", own: true, name: "Ada's workspace" });
    expect(list.map((w) => w.role)).toEqual(["owner", "normal", "admin", "normal"]);
    expect(list.some((w) => w.tenantId === "t8")).toBe(false);
  });

  it("sorts with the locale-aware comparison of the given language", () => {
    const rows = [membership("a", "Zebra", "normal"), membership("b", "ápple", "normal"), membership("c", "Apple", "normal")];
    const expected = [...rows].sort((x, y) => x.tenantName.localeCompare(y.tenantName, "en")).map((r) => r.tenantId);
    expect(buildWorkspaceList(own, rows, "en").slice(1).map((w) => w.tenantId)).toEqual(expected);
  });

  it("does not list the own workspace twice", () => {
    expect(buildWorkspaceList(own, [OWN], "en")).toHaveLength(1);
  });
});
