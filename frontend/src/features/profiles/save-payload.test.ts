import { describe, expect, it } from "vitest";
import {
  toCreateProfilePayload,
  toUpdateProfilePayload,
  type ProfileFormValues,
} from "./save-payload";

const values: ProfileFormValues = {
  name: "Late-night reads",
  avatarKey: "ember",
  mood: "horror",
  matureEnabled: true,
};

describe("toCreateProfilePayload", () => {
  it("carries the mature-content gate into POST /profiles", () => {
    expect(toCreateProfilePayload(values)).toEqual({
      name: "Late-night reads",
      avatar_key: "ember",
      mood: "horror",
      mature_content_enabled: true,
    });
  });

  it("leaves sort_order to the backend", () => {
    expect(
      "sort_order" in (toCreateProfilePayload(values) as Record<string, unknown>),
    ).toBe(false);
  });
});

describe("toUpdateProfilePayload", () => {
  it("carries the mature-content gate into PATCH /profiles/{id}", () => {
    expect(toUpdateProfilePayload({ ...values, matureEnabled: false })).toEqual({
      name: "Late-night reads",
      avatar_key: "ember",
      mood: "horror",
      mature_content_enabled: false,
    });
  });

  it("never touches sort_order (reordering is not the dialog's job)", () => {
    expect(
      "sort_order" in (toUpdateProfilePayload(values) as Record<string, unknown>),
    ).toBe(false);
  });
});
