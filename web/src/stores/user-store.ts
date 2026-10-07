import { create } from "zustand";
import type { SessionUser } from "@/interfaces/user";

interface UserState {
  userId: string | null;
  /** The recovered signed-in user; null until session recovery succeeds. */
  user: SessionUser | null;
  setUserId: (userId: string | null) => void;
  setUser: (user: SessionUser) => void;
  clearUser: () => void;
  reset: () => void;
}

export const useUserStore = create<UserState>()((set) => ({
  userId: null,
  user: null,
  setUserId: (userId) => set({ userId }),
  setUser: (user) => set({ user, userId: user.id }),
  clearUser: () => set({ user: null, userId: null }),
  reset: () => set({ user: null, userId: null }),
}));
