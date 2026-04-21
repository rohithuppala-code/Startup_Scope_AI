"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useUserStore } from "@/stores/user-store";

export function useAuth({ redirectTo = "/login" } = {}) {
  const { isAuthenticated, userId, email, karma, badges, logout: storeLogout } =
    useUserStore();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTimeout(() => setMounted(true), 0);
  }, []);

  useEffect(() => {
    if (mounted && !isAuthenticated) {
      router.replace(redirectTo);
    }
  }, [mounted, isAuthenticated, redirectTo, router]);

  const logout = useCallback(() => {
    storeLogout();
    router.replace("/login");
  }, [storeLogout, router]);

  return { isAuthenticated, userId, email, karma, badges, logout, isLoaded: mounted };
}
