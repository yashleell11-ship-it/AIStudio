"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/types/api";
import { resolveLoginScreenMode } from "../access";
import { useBootstrapStatus, useCurrentUser } from "../hooks";
import { AuthCard } from "./auth-card";
import { AuthPending } from "./auth-pending";
import { LoginForm } from "./login-form";
import { RegisterForm } from "./register-form";

/**
 * The sign-in screen. Before an account exists it doubles as first-run setup
 * and shows the create-first-admin form. Already-authenticated visitors are
 * bounced home.
 */
export function LoginScreen() {
  const router = useRouter();
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const bootstrap = useBootstrapStatus();

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  // Hold the frame while the session resolves, or while bouncing an
  // already-authenticated visitor home — never flash the form at them.
  if (userLoading || bootstrap.isLoading || user) {
    return <AuthPending />;
  }

  if (bootstrap.isError || !bootstrap.data) {
    return (
      <AuthCard title="ManhwaManiacs" subtitle="We couldn't reach the server.">
        <div className="space-y-4 text-center">
          <p className="text-sm text-danger">
            {bootstrap.error instanceof ApiError
              ? bootstrap.error.message
              : "Could not load the sign-in page. Check that the backend is running."}
          </p>
          <Button variant="secondary" className="w-full" onClick={() => bootstrap.refetch()}>
            Try again
          </Button>
        </div>
      </AuthCard>
    );
  }

  if (resolveLoginScreenMode(bootstrap.data) === "bootstrap") {
    return (
      <AuthCard
        title="Welcome to ManhwaManiacs"
        subtitle="Create the first account to finish setup. It becomes the administrator."
      >
        <RegisterForm bootstrap />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to your ManhwaManiacs library."
      footer={
        bootstrap.data.registration_enabled ? (
          <>
            Need an account?{" "}
            <Link href="/register" className="font-medium text-violet-400 hover:text-violet-300">
              Create one
            </Link>
          </>
        ) : null
      }
    >
      <LoginForm />
    </AuthCard>
  );
}
