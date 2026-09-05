"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  CHANGE_PASSWORD_FIELDS,
  MIN_PASSWORD_LENGTH,
  describeAuthError,
  fieldsToClearAfterFailure,
  toChangePasswordPayload,
  validateChangePassword,
  type ChangePasswordField,
  type ChangePasswordFormValues,
} from "../account-security";
import { useChangePassword } from "../hooks";
import { PasswordInput } from "./password-input";

const EMPTY: ChangePasswordFormValues = {
  currentPassword: "",
  newPassword: "",
  confirmPassword: "",
};

/**
 * Rotate this account's password.
 *
 * The three secrets live in component state for exactly as long as the request
 * needs them: a success wipes all three, a failure wipes whichever the server
 * rejected (`fieldsToClearAfterFailure`), and `changePassword.reset()` runs
 * either way because react-query otherwise keeps the submitted `variables` —
 * the request body, password included — on the mutation until the next one.
 */
export function ChangePasswordForm() {
  const changePassword = useChangePassword();
  const [values, setValues] = useState<ChangePasswordFormValues>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  const setField = (field: ChangePasswordField) => (value: string) => {
    setError(null);
    setChanged(false);
    setValues((current) => ({ ...current, [field]: value }));
  };

  const clearFields = (fields: readonly ChangePasswordField[]) => {
    setValues((current) => {
      const next = { ...current };
      for (const field of fields) next[field] = "";
      return next;
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (changePassword.isPending) return;

    setChanged(false);
    const invalid = validateChangePassword(values);
    if (invalid) {
      setError(invalid);
      return;
    }

    setError(null);
    try {
      await changePassword.mutateAsync(toChangePasswordPayload(values));
      clearFields(CHANGE_PASSWORD_FIELDS);
      setChanged(true);
    } catch (failure) {
      setError(describeAuthError(failure, "Could not change the password. Please try again."));
      clearFields(fieldsToClearAfterFailure(failure));
    } finally {
      changePassword.reset();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <label htmlFor="account-current-password" className="text-sm font-medium text-fg">
          Current password
        </label>
        <PasswordInput
          id="account-current-password"
          name="current-password"
          autoComplete="current-password"
          value={values.currentPassword}
          onChange={(event) => setField("currentPassword")(event.target.value)}
          placeholder="Your current password"
          disabled={changePassword.isPending}
          required
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="account-new-password" className="text-sm font-medium text-fg">
          New password
        </label>
        <PasswordInput
          id="account-new-password"
          name="new-password"
          autoComplete="new-password"
          value={values.newPassword}
          onChange={(event) => setField("newPassword")(event.target.value)}
          placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
          disabled={changePassword.isPending}
          required
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="account-confirm-password" className="text-sm font-medium text-fg">
          Confirm new password
        </label>
        <PasswordInput
          id="account-confirm-password"
          name="confirm-new-password"
          autoComplete="new-password"
          value={values.confirmPassword}
          onChange={(event) => setField("confirmPassword")(event.target.value)}
          placeholder="Type it again"
          disabled={changePassword.isPending}
          required
        />
      </div>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {changed ? (
        <p role="status" className="text-sm text-primary">
          Password changed. Every other device has been signed out — this one stays
          signed in.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={changePassword.isPending}>
          <KeyRound className="size-4" aria-hidden />
          {changePassword.isPending ? "Changing…" : "Change password"}
        </Button>
        <p className="text-xs text-muted">
          Changing it signs out every other device. This one stays signed in.
        </p>
      </div>
    </form>
  );
}
