import { describe, expect, it } from "vitest";
import type { TwoFactorStatus } from "@/types/api/admin";
import { backupCodeInput, backupCodesText, gateScreen, groupKey, msBeforeExpiry, onlyDigits } from "./rules";

const NOW = Date.parse("2026-11-20T12:00:00Z");
const status = (fields: Partial<TwoFactorStatus> = {}): TwoFactorStatus => ({
  enabled: true, enabled_at: "2026-11-01T08:00:00Z", verified_at: null, expires_at: null, backup_codes_left: 10,
  ...fields,
});
const gate = (fields: Partial<Parameters<typeof gateScreen>[0]> = {}) =>
  gateScreen({ isAdmin: true, loading: false, status: status(), now: NOW, ...fields });

describe("gateScreen", () => {
  it("never stops an account that is not an admin", () => {
    expect(gate({ isAdmin: false, status: status({ enabled: false }) })).toBe("open");
  });

  it("waits for the status, and lets the API judge when it cannot be read", () => {
    expect(gate({ loading: true })).toBe("loading");
    expect(gate({ status: undefined })).toBe("open");
  });

  it("asks to set up the second factor before anything else", () => {
    expect(gate({ status: status({ enabled: false }) })).toBe("setup");
  });

  it("asks for the code until verified, and again once expired", () => {
    expect(gate()).toBe("code");
    expect(gate({ status: status({ verified_at: "2026-11-20T08:00:00Z", expires_at: "2026-11-20T20:00:00Z" }) })).toBe("open");
    expect(gate({ status: status({ verified_at: "2026-11-19T23:00:00Z", expires_at: "2026-11-20T11:00:00Z" }) })).toBe("code");
  });
});

describe("msBeforeExpiry", () => {
  it("counts down to the expiry, null once passed or without verification", () => {
    expect(msBeforeExpiry(status({ expires_at: "2026-11-20T12:01:00Z" }), NOW)).toBe(60_000);
    expect(msBeforeExpiry(status({ expires_at: "2026-11-20T11:00:00Z" }), NOW)).toBeNull();
    expect(msBeforeExpiry(status(), NOW)).toBeNull();
    expect(msBeforeExpiry(undefined, NOW)).toBeNull();
  });
});

describe("inputs", () => {
  it("groups the setup key by 4", () => {
    expect(groupKey("JBSWY3DPEHPK3PXP")).toBe("JBSW Y3DP EHPK 3PXP");
  });

  it("keeps 6 digits of a typed or pasted code", () => {
    expect(onlyDigits(" 482 913 7")).toBe("482913");
  });

  it("cleans a backup code being typed", () => {
    expect(backupCodeInput("k7qf-92xm !")).toBe("K7QF-92XM");
  });
});

it("writes the backup codes file", () => {
  const text = backupCodesText(["K7QF-92XM", "3HVD-T8LP"], "admin@kwa-ba.com", new Date(NOW));
  expect(text).toContain("Compte : admin@kwa-ba.com");
  expect(text).toContain("01  K7QF-92XM\n02  3HVD-T8LP");
});
