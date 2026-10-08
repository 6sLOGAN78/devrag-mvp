import { create } from "zustand";
import type { Membership } from "@/services/team-service";

/** localStorage key of the remembered workspace: `{ userId, tenantId }` (D-26). */
export const WORKSPACE_STORAGE_KEY = "devrag.workspace";

interface StoredWorkspace {
  userId: string;
  tenantId: string;
}

/**
 * Set only when the browser refused to store the choice (blocked site data, quota, policy): the choice then lives
 * here for the lifetime of the tab. When storage works it is always null and storage is the single truth.
 */
let memoryEntry: StoredWorkspace | null = null;

function parseStored(raw: string | null): StoredWorkspace | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
    const { userId, tenantId } = value as Record<string, unknown>;
    if (typeof userId !== "string" || typeof tenantId !== "string" || userId === "" || tenantId === "") return null;
    return { userId, tenantId };
  } catch {
    return null;
  }
}

/** The stored value is untrusted input (T-03-03-01): shape-checked here, membership-checked by the caller. */
function readStored(): StoredWorkspace | null {
  if (memoryEntry !== null) return memoryEntry;
  try {
    return parseStored(localStorage.getItem(WORKSPACE_STORAGE_KEY));
  } catch {
    // Storage blocked: behave as if nothing was stored rather than crash the render tree.
    return null;
  }
}

function writeStored(entry: StoredWorkspace): void {
  try {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(entry));
    memoryEntry = null;
  } catch {
    memoryEntry = entry;
  }
}

function clearStored(): void {
  memoryEntry = null;
  try {
    localStorage.removeItem(WORKSPACE_STORAGE_KEY);
  } catch {
    /* storage blocked: nothing persisted, nothing to remove */
  }
}

/** Roles of a workspace the caller joined. `invite` is a pending invitation and is never a workspace. */
const JOINED_ROLES: ReadonlySet<string> = new Set(["admin", "normal"]);

function joinedOf(memberships: readonly Membership[], ownTenantId: string): Membership[] {
  return memberships.filter((row) => JOINED_ROLES.has(row.role) && row.tenantId !== ownTenantId);
}

/** One entry of the workspace menu. */
export interface Workspace {
  tenantId: string;
  name: string;
  /** `owner` for the caller's own workspace, otherwise `admin` or `normal`. */
  role: string;
  ownerNickname: string;
  own: boolean;
}

export interface OwnWorkspace {
  tenantId: string;
  name: string;
  ownerNickname: string;
}

/** The caller's own workspace first, then joined workspaces (admin or normal) by name in the language's order. */
export function buildWorkspaceList(own: OwnWorkspace, memberships: readonly Membership[], language: string): Workspace[] {
  const joined = joinedOf(memberships, own.tenantId)
    .map<Workspace>((row) => ({ tenantId: row.tenantId, name: row.tenantName, role: row.role, ownerNickname: row.ownerNickname, own: false }))
    .sort((a, b) => a.name.localeCompare(b.name, language));
  return [{ tenantId: own.tenantId, name: own.name, role: "owner", ownerNickname: own.ownerNickname, own: true }, ...joined];
}

interface WorkspaceState {
  /** The workspace every Phase 3 page acts in; null until the list has loaded. Callers fall back to the own workspace. */
  activeTenantId: string | null;
  /** The signed-in user the state was initialised for. */
  initialisedFor: string | null;
  ownTenantId: string | null;
  /** The last server list, kept to name a workspace that later disappears. */
  memberships: Membership[];
  /** Name of the workspace the caller just lost access to; the toast reads and clears it. */
  lost: string | null;
  initialise: (userId: string, ownTenantId: string, memberships: readonly Membership[]) => void;
  setActive: (tenantId: string) => void;
  setMemberships: (memberships: readonly Membership[]) => void;
  clearLost: () => void;
  reset: () => void;
}

const EMPTY = { activeTenantId: null, initialisedFor: null, ownTenantId: null, memberships: [], lost: null } as const;

export const useWorkspaceStore = create<WorkspaceState>()((set, get) => ({
  ...EMPTY,
  memberships: [],

  initialise: (userId, ownTenantId, memberships) => {
    const allowed = new Set([ownTenantId, ...joinedOf(memberships, ownTenantId).map((row) => row.tenantId)]);
    const stored = readStored();
    // Only this user's own entry counts, and only for a workspace the server still lists (T-03-03-01, -02).
    const remembered = stored !== null && stored.userId === userId && allowed.has(stored.tenantId) ? stored.tenantId : null;
    set({ activeTenantId: remembered ?? ownTenantId, initialisedFor: userId, ownTenantId, memberships: [...memberships], lost: null });
  },

  setActive: (tenantId) => {
    const { initialisedFor, ownTenantId, memberships } = get();
    if (initialisedFor === null || ownTenantId === null) return;
    const allowed = tenantId === ownTenantId || joinedOf(memberships, ownTenantId).some((row) => row.tenantId === tenantId);
    if (!allowed) return;
    set({ activeTenantId: tenantId });
    writeStored({ userId: initialisedFor, tenantId });
  },

  setMemberships: (next) => {
    const { activeTenantId, ownTenantId, memberships: previous, initialisedFor } = get();
    if (ownTenantId === null || initialisedFor === null) return;
    const stillListed = activeTenantId === null || activeTenantId === ownTenantId || joinedOf(next, ownTenantId).some((row) => row.tenantId === activeTenantId);
    if (stillListed) {
      set({ memberships: [...next] });
      return;
    }
    const lostName = previous.find((row) => row.tenantId === activeTenantId)?.tenantName;
    set({ memberships: [...next], activeTenantId: ownTenantId, lost: lostName && lostName !== "" ? lostName : (activeTenantId ?? "") });
    writeStored({ userId: initialisedFor, tenantId: ownTenantId });
  },

  clearLost: () => set({ lost: null }),

  reset: () => {
    clearStored();
    set({ ...EMPTY, memberships: [] });
  },
}));
