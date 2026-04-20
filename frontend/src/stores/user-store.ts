import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "@/lib/api";

interface UserState {
  userId: string | null;
  email: string | null;
  accessToken: string | null;
  refreshToken: string | null;
  karma: number;
  badges: string[];
  isAuthenticated: boolean;

  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setKarma: (karma: number) => void;
  setBadges: (badges: string[]) => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      userId: null,
      email: null,
      accessToken: null,
      refreshToken: null,
      karma: 0,
      badges: [],
      isAuthenticated: false,

      login: async (email: string, password: string) => {
        const data = await api<{
          user_id: string;
          email: string;
          access_token: string;
          refresh_token: string;
        }>("/api/v1/auth/login", {
          method: "POST",
          body: { email, password },
        });
        set({
          userId: data.user_id,
          email: data.email,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
          isAuthenticated: true,
        });
      },

      logout: () =>
        set({
          userId: null,
          email: null,
          accessToken: null,
          refreshToken: null,
          karma: 0,
          badges: [],
          isAuthenticated: false,
        }),

      setKarma: (karma) => set({ karma }),
      setBadges: (badges) => set({ badges }),
    }),
    { name: "startupscope-user" }
  )
);
