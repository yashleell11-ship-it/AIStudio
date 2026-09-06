import { beforeEach, describe, expect, it, vi } from "vitest";
import { http } from "@/services/http";
import { adminApi } from "./api";
import type { MemberAccount } from "./types";

// The wrappers are the whole contract with the backend agent's routes, so the
// fetch helper is mocked and every path, method and body is pinned here.
vi.mock("@/services/http", () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mocked = vi.mocked(http);

function member(overrides: Partial<MemberAccount> = {}): MemberAccount {
  return {
    id: 7,
    username: "friend",
    is_admin: false,
    is_active: true,
    created_at: "2026-09-02 10:00:00",
    last_login_at: null,
    session_count: 0,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("adminApi.users", () => {
  it("lists every account from GET /auth/users", async () => {
    const rows = [member()];
    mocked.get.mockResolvedValueOnce(rows);
    await expect(adminApi.users()).resolves.toBe(rows);
    expect(mocked.get).toHaveBeenCalledTimes(1);
    expect(mocked.get).toHaveBeenCalledWith("/auth/users");
  });
});

describe("adminApi.setActive", () => {
  it("deactivates with PATCH /auth/users/{id} and {is_active: false}", async () => {
    const updated = member({ is_active: false });
    mocked.patch.mockResolvedValueOnce(updated);
    await expect(adminApi.setActive(7, false)).resolves.toBe(updated);
    expect(mocked.patch).toHaveBeenCalledWith("/auth/users/7", { is_active: false });
  });

  it("reactivates with the same route and {is_active: true}", async () => {
    mocked.patch.mockResolvedValueOnce(member({ is_active: true }));
    await adminApi.setActive(7, true);
    expect(mocked.patch).toHaveBeenCalledWith("/auth/users/7", { is_active: true });
  });

  it("sends exactly the one field the route accepts", async () => {
    mocked.patch.mockResolvedValueOnce(member());
    await adminApi.setActive(7, false);
    const [, body] = mocked.patch.mock.calls[0];
    expect(Object.keys(body as object)).toEqual(["is_active"]);
  });

  it("puts the id in the path, never the query string", async () => {
    mocked.patch.mockResolvedValueOnce(member());
    await adminApi.setActive(42, false);
    const [path, , options] = mocked.patch.mock.calls[0];
    expect(path).toBe("/auth/users/42");
    expect(options).toBeUndefined();
  });
});

describe("adminApi.deleteUser", () => {
  it("removes an account with DELETE /auth/users/{id}", async () => {
    mocked.delete.mockResolvedValueOnce(undefined);
    await expect(adminApi.deleteUser(7)).resolves.toBeUndefined();
    expect(mocked.delete).toHaveBeenCalledWith("/auth/users/7");
  });

  it("surfaces the server's refusal untouched", async () => {
    const refused = new Error("You cannot delete your own account.");
    mocked.delete.mockRejectedValueOnce(refused);
    await expect(adminApi.deleteUser(1)).rejects.toBe(refused);
  });
});
