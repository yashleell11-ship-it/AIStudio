import type { RegisterPayload } from "./types";

/** What the register form collects before submitting. */
export interface RegisterFormValues {
  username: string;
  password: string;
  confirmPassword: string;
  email: string;
  displayName: string;
  inviteCode: string;
  remember: boolean;
}

/** True when the password and confirmation fields agree (both compared as-is). */
export function passwordsMatch(
  values: Pick<RegisterFormValues, "password" | "confirmPassword">,
): boolean {
  return values.password === values.confirmPassword;
}

/**
 * Body for `POST /auth/register`. Trims free-text fields and turns a blank
 * optional field into `null` (matches the login/register convention already
 * used for email/display_name); `confirmPassword` never leaves the client —
 * it exists only to catch a typo before submitting.
 */
export function toRegisterPayload(values: RegisterFormValues): RegisterPayload {
  return {
    username: values.username.trim(),
    password: values.password,
    email: values.email.trim() || null,
    display_name: values.displayName.trim() || null,
    invite_code: values.inviteCode.trim() || null,
    remember: values.remember,
  };
}
