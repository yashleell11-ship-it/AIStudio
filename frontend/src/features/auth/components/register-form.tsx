"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/types/api";
import { useRegister } from "../hooks";
import { PasswordInput } from "./password-input";

interface RegisterFormProps {
  /** When true this creates the first (admin) account rather than a normal one. */
  bootstrap: boolean;
}

/** Dark surface field with an amber focus ring, matching the Eclipse Warm auth inputs. */
const authInputClass =
  "bg-surface border-border focus-visible:border-primary/40 focus-visible:ring-primary";

/** Account creation. Redirects home on success; errors inline. */
export function RegisterForm({ bootstrap }: RegisterFormProps) {
  const router = useRouter();
  const register = useRegister();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [remember, setRemember] = useState(true);

  const canSubmit = !register.isPending && username.trim() !== "" && password !== "";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    try {
      await register.mutateAsync({
        username: username.trim(),
        password,
        email: email.trim() || null,
        display_name: displayName.trim() || null,
        remember,
      });
      router.replace("/");
    } catch {
      // Surfaced below via `register.error`.
    }
  };

  const error = register.error
    ? register.error instanceof ApiError
      ? register.error.message
      : "Could not create the account. Please try again."
    : null;

  const SubmitIcon = bootstrap ? ShieldCheck : UserPlus;
  const submitLabel = bootstrap ? "Create admin account" : "Create account";

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <label htmlFor="register-username" className="text-sm font-medium text-fg">
          Username
        </label>
        <Input
          id="register-username"
          name="username"
          autoComplete="username"
          autoFocus
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="yourname"
          disabled={register.isPending}
          className={authInputClass}
          required
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="register-password" className="text-sm font-medium text-fg">
          Password
        </label>
        <PasswordInput
          id="register-password"
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Choose a password"
          disabled={register.isPending}
          className={authInputClass}
          required
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="register-display-name" className="text-sm font-medium text-fg">
          Display name <span className="font-normal text-muted">(optional)</span>
        </label>
        <Input
          id="register-display-name"
          name="display-name"
          autoComplete="nickname"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="How your name appears"
          disabled={register.isPending}
          className={authInputClass}
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="register-email" className="text-sm font-medium text-fg">
          Email <span className="font-normal text-muted">(optional)</span>
        </label>
        <Input
          id="register-email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          disabled={register.isPending}
          className={authInputClass}
        />
      </div>

      <div className="flex items-center justify-between">
        <label htmlFor="register-remember" className="text-sm text-muted">
          Keep me signed in
        </label>
        <Switch
          id="register-remember"
          checked={remember}
          onCheckedChange={setRemember}
          disabled={register.isPending}
          aria-label="Keep me signed in"
        />
      </div>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      <Button
        type="submit"
        size="lg"
        className="w-full rounded-full uppercase tracking-wide text-white cta-gradient hover:brightness-110"
        disabled={!canSubmit}
      >
        {register.isPending ? (
          "Creating account…"
        ) : (
          <>
            <SubmitIcon className="size-4" aria-hidden />
            {submitLabel}
          </>
        )}
      </Button>
    </form>
  );
}
