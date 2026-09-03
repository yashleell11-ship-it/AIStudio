"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { describeRegisterError } from "../access";
import { useRegister } from "../hooks";
import { passwordsMatch, toRegisterPayload, type RegisterFormValues } from "../register-payload";
import { PasswordInput } from "./password-input";

interface RegisterFormProps {
  /** When true this creates the first (admin) account rather than a normal one. */
  bootstrap: boolean;
  /**
   * Whether the server requires an invite code for this registration. Ignored
   * (and the field never shown) during bootstrap — the first account never
   * needs one.
   */
  showInviteCode?: boolean;
}

/** Dark surface field with an amber focus ring, matching the Eclipse Warm auth inputs. */
const authInputClass =
  "bg-surface border-border focus-visible:border-primary/40 focus-visible:ring-primary";

/** Account creation. Redirects home on success; errors inline. */
export function RegisterForm({ bootstrap, showInviteCode = false }: RegisterFormProps) {
  const router = useRouter();
  const register = useRegister();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [remember, setRemember] = useState(true);

  // Bootstrap never needs a code, regardless of what the caller passes — the
  // first account on an instance always succeeds without one.
  const displayInvite = showInviteCode && !bootstrap;

  const passwordsTyped = password !== "" && confirmPassword !== "";
  const passwordMismatch = passwordsTyped && !passwordsMatch({ password, confirmPassword });

  const canSubmit =
    !register.isPending &&
    username.trim() !== "" &&
    password !== "" &&
    confirmPassword !== "" &&
    !passwordMismatch &&
    (!displayInvite || inviteCode.trim() !== "");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    const values: RegisterFormValues = {
      username,
      password,
      confirmPassword,
      email,
      displayName,
      inviteCode,
      remember,
    };
    try {
      await register.mutateAsync(toRegisterPayload(values));
      router.replace("/");
    } catch {
      // Surfaced below via `register.error`.
    }
  };

  const error = register.error ? describeRegisterError(register.error) : null;

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
        <label htmlFor="register-confirm-password" className="text-sm font-medium text-fg">
          Confirm password
        </label>
        <PasswordInput
          id="register-confirm-password"
          name="confirm-password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          placeholder="Type it again"
          disabled={register.isPending}
          className={authInputClass}
          aria-invalid={passwordMismatch}
          required
        />
        {passwordMismatch ? (
          <p role="alert" className="text-sm text-danger">
            Passwords don&apos;t match.
          </p>
        ) : null}
      </div>

      {displayInvite ? (
        <div className="space-y-1.5">
          <label htmlFor="register-invite-code" className="text-sm font-medium text-fg">
            Invite code
          </label>
          <Input
            id="register-invite-code"
            name="invite-code"
            autoComplete="off"
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value)}
            placeholder="Ask whoever invited you"
            disabled={register.isPending}
            className={authInputClass}
            required
          />
        </div>
      ) : null}

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
