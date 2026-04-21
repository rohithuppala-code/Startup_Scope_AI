"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useUserStore } from "@/stores/user-store";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTimeout(() => setMounted(true), 0);
  }, []);

  useEffect(() => {
    if (mounted && !isAuthenticated && !pathname.startsWith("/login") && !pathname.startsWith("/register")) {
      router.replace("/login");
    }
  }, [mounted, isAuthenticated, router, pathname]);

  if (!mounted) return null;
  if (!isAuthenticated && !pathname.startsWith("/login") && !pathname.startsWith("/register")) return null;

  return <>{children}</>;
}
