"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/types/api";
import { useLogin } from "../hooks";
import { PasswordInput } from "./password-input";

/** Username + password sign-in. Redirects home on success; errors inline. */
export function LoginForm() {
  const router = useRouter();
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);

  const canSubmit = !login.isPending && username.trim() !== "" && password !== "";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    try {
      await login.mutateAsync({ username: username.trim(), password, remember });
      router.replace("/");
    } catch {
      // Surfaced below via `login.error`.
    }
  };

  const error = login.error
    ? login.error instanceof ApiError
      ? login.error.message
      : "Could not sign in. Please try again."
    : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <label htmlFor="login-username" className="text-sm font-medium text-fg">
          Username
        </label>
        <Input
          id="login-username"
          name="username"
          autoComplete="username"
          autoFocus
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="yourname"
          disabled={login.isPending}
          required
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="login-password" className="text-sm font-medium text-fg">
          Password
        </label>
        <PasswordInput
          id="login-password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Your password"
          disabled={login.isPending}
          required
        />
      </div>

      <div className="flex items-center justify-between">
        <label htmlFor="login-remember" className="text-sm text-muted">
          Keep me signed in
        </label>
        <Switch
          id="login-remember"
          checked={remember}
          onCheckedChange={setRemember}
          disabled={login.isPending}
          aria-label="Keep me signed in"
        />
      </div>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      <Button type="submit" size="lg" className="w-full" disabled={!canSubmit}>
        {login.isPending ? (
          "Signing in…"
        ) : (
          <>
            <LogIn className="size-4" aria-hidden />
            Sign in
          </>
        )}
      </Button>
    </form>
  );
}
