"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUserStore } from "@/stores/user-store";

export default function RootPage() {
  const router = useRouter();
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);

  useEffect(() => {
    router.replace(isAuthenticated ? "/nexus" : "/login");
  }, [isAuthenticated, router]);

  return null;
}
