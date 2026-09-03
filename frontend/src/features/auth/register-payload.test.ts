import { describe, expect, it } from "vitest";
import { passwordsMatch, toRegisterPayload, type RegisterFormValues } from "./register-payload";

function values(overrides: Partial<RegisterFormValues> = {}): RegisterFormValues {
  return {
    username: "yash",
    password: "correct-horse-battery-staple",
    confirmPassword: "correct-horse-battery-staple",
    email: "",
    displayName: "",
    inviteCode: "",
    remember: true,
    ...overrides,
  };
}

describe("passwordsMatch", () => {
  it("is true when both fields are identical", () => {
    expect(
      passwordsMatch({ password: "hunter22", confirmPassword: "hunter22" }),
    ).toBe(true);
  });

  it("is false when they differ", () => {
    expect(
      passwordsMatch({ password: "hunter22", confirmPassword: "hunter23" }),
    ).toBe(false);
  });
});

describe("toRegisterPayload", () => {
  it("builds the happy-path payload: trimmed username, verbatim password, no optional fields", () => {
    expect(toRegisterPayload(values({ username: "  yash  " }))).toEqual({
      username: "yash",
      password: "correct-horse-battery-staple",
      email: null,
      display_name: null,
      invite_code: null,
      remember: true,
    });
  });

  it("never sends confirmPassword to the server", () => {
    expect(Object.keys(toRegisterPayload(values()))).not.toContain("confirmPassword");
  });

  it("trims and carries optional email, display name, and invite code when present", () => {
    expect(
      toRegisterPayload(
        values({
          email: "  yash@example.com  ",
          displayName: "  Yash  ",
          inviteCode: "  amber-fox  ",
        }),
      ),
    ).toMatchObject({
      email: "yash@example.com",
      display_name: "Yash",
      invite_code: "amber-fox",
    });
  });

  it("nulls a blank invite code rather than sending an empty string", () => {
    expect(toRegisterPayload(values({ inviteCode: "   " })).invite_code).toBeNull();
  });

  it("carries the remember flag through", () => {
    expect(toRegisterPayload(values({ remember: false })).remember).toBe(false);
  });
});
