"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useUserStore } from "@/stores/user-store";
import LoginPage from "./(auth)/login/page";
import AuthLayout from "./(auth)/layout";

export default function RootPage() {
  const router = useRouter();
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (isAuthenticated) {
      router.replace("/nexus");
    }
  }, [isAuthenticated, router]);

  // Prevent hydration mismatch
  if (!mounted) return null;

  if (isAuthenticated) {
    return null;
  }

  // Render the login page exactly as it appears at /login
  return (
    <AuthLayout>
      <LoginPage />
    </AuthLayout>
  );
}
