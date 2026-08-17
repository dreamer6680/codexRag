import { describe, expect, it } from "vitest";
import { accessTokenFromSession } from "./session";

describe("accessTokenFromSession", () => {
  it("returns null instead of forwarding an unauthenticated request", () => {
    expect(accessTokenFromSession(null)).toBeNull();
  });

  it("returns only the access token from a valid session", () => {
    expect(accessTokenFromSession({ access_token: "verified-token" })).toBe("verified-token");
  });
});
