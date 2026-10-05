import { create } from "zustand";

interface UserState {
  userId: string | null;
  setUserId: (userId: string | null) => void;
  reset: () => void;
}

export const useUserStore = create<UserState>()((set) => ({
  userId: null,
  setUserId: (userId) => set({ userId }),
  reset: () => set({ userId: null }),
}));
