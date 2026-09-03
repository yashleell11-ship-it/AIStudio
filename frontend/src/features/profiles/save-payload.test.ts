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
    expect(Object.keys(toCreateProfilePayload(values))).not.toContain(
      "sort_order",
    );
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
    expect(Object.keys(toUpdateProfilePayload(values))).not.toContain(
      "sort_order",
    );
  });
});
