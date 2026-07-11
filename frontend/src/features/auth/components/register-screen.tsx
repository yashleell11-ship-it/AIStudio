"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/types/api";
import { resolveRegisterAvailability } from "../access";
import { useBootstrapStatus, useCurrentUser } from "../hooks";
import { AuthCard } from "./auth-card";
import { AuthPending } from "./auth-pending";
import { RegisterForm } from "./register-form";

/**
 * The account-creation screen. Reachable for first-admin bootstrap and for
 * open self-registration; when registration is closed it explains that and
 * points back to sign-in. Already-authenticated visitors are bounced home.
 */
export function RegisterScreen() {
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
      <AuthCard title="Create your account" subtitle="We couldn't reach the server.">
        <div className="space-y-4 text-center">
          <p className="text-sm text-danger">
            {bootstrap.error instanceof ApiError
              ? bootstrap.error.message
              : "Could not load the registration page. Check that the backend is running."}
          </p>
          <Button variant="secondary" className="w-full" onClick={() => bootstrap.refetch()}>
            Try again
          </Button>
        </div>
      </AuthCard>
    );
  }

  const availability = resolveRegisterAvailability(bootstrap.data);

  if (availability === "closed") {
    return (
      <AuthCard
        title="Registration closed"
        subtitle="This ManhwaManiacs instance isn't accepting new accounts."
      >
        <div className="space-y-4 text-center">
          <p className="text-sm text-muted">
            Ask an administrator to create an account for you, then sign in.
          </p>
          <Button variant="secondary" className="w-full" onClick={() => router.push("/login")}>
            Back to sign in
          </Button>
        </div>
      </AuthCard>
    );
  }

  const isBootstrap = availability === "bootstrap";

  return (
    <AuthCard
      title={isBootstrap ? "Create the first account" : "Create your account"}
      subtitle={
        isBootstrap
          ? "This first account becomes the administrator."
          : "Join this ManhwaManiacs library."
      }
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-violet-400 hover:text-violet-300">
            Sign in
          </Link>
        </>
      }
    >
      <RegisterForm bootstrap={isBootstrap} />
    </AuthCard>
  );
}
