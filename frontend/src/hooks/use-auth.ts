"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUserStore } from "@/stores/user-store";

export function useAuth({ redirectTo = "/login" } = {}) {
  const { isAuthenticated, userId, email, karma, badges, logout } =
    useUserStore();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated) router.replace(redirectTo);
  }, [isAuthenticated, redirectTo, router]);

  return { isAuthenticated, userId, email, karma, badges, logout };
}
