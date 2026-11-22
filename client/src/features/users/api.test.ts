import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "@/lib/api";
import {
  accountDeletionBlockers, confirmTwoFactorSetup, deleteMyAccount, lireDroitsAdmin, lireMoi, lireStatsAdmin, modifierMoi, modifierUtilisateurAdmin,
  ouvrirCandidature, readTwoFactorStatus, requestAccountDeletionCode, resetTwoFactor, startTwoFactorSetup,
} from "./api";

vi.mock("@/lib/api", () => ({
  default: { get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() },
  estErreurApi: (err: unknown) => Boolean((err as { isAxiosError?: boolean } | null)?.isAxiosError),
}));

describe("users", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.patch]) vi.mocked(m).mockResolvedValue({ data: { first_name: "Kossi" } });
  });

  it("lit et modifie son compte", async () => {
    await expect(lireMoi()).resolves.toEqual({ first_name: "Kossi" });
    expect(api.get).toHaveBeenLastCalledWith("/v1/users/me/");
    await modifierMoi({ first_name: "Ama", phone: null });
    expect(api.patch).toHaveBeenLastCalledWith("/v1/users/me/", { first_name: "Ama", phone: null });
  });

  it("ouvre une candidature", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: {} });
    await ouvrirCandidature();
    expect(api.post).toHaveBeenLastCalledWith("/v1/users/me/candidature/");
  });

  it("deletes the account with the emailed code", async () => {
    await requestAccountDeletionCode();
    expect(api.post).toHaveBeenLastCalledWith("/v1/users/me/deletion-code/");
    await deleteMyAccount("123456");
    expect(api.delete).toHaveBeenCalledWith("/v1/users/me/", { data: { code: "123456" } });
  });

  it("reads why a deletion is refused", () => {
    const blockers = [{ code: "upcoming_stays", detail: "Vous avez un séjour à venir." }];
    const refus = { isAxiosError: true, response: { status: 409, data: { code: "account_deletion_blocked", blockers } } };
    expect(accountDeletionBlockers(refus)).toEqual(blockers);
    expect(accountDeletionBlockers({ isAxiosError: true, response: { status: 400, data: {} } })).toEqual([]);
    expect(accountDeletionBlockers(new Error("réseau"))).toEqual([]);
  });

  it("gère les comptes depuis le back-office", async () => {
    await modifierUtilisateurAdmin("u1", { is_active: false });
    await lireDroitsAdmin();
    expect(api.get).toHaveBeenCalledWith("/v1/admin/droits/");
    expect(api.patch).toHaveBeenLastCalledWith("/v1/admin/users/u1/", { is_active: false });
    await lireStatsAdmin();
    expect(api.get).toHaveBeenLastCalledWith("/v1/admin/stats/");
  });

  it("gère la double authentification", async () => {
    await readTwoFactorStatus();
    expect(api.get).toHaveBeenLastCalledWith("/v1/auth/two-factor/");
    vi.mocked(api.post).mockResolvedValueOnce({ data: { otpauth_uri: "otpauth://totp/x", secret: "S" } });
    await expect(startTwoFactorSetup()).resolves.toEqual({ otpauth_uri: "otpauth://totp/x", secret: "S" });
    expect(api.post).toHaveBeenLastCalledWith("/v1/auth/two-factor/setup/");
    vi.mocked(api.post).mockResolvedValueOnce({ data: { backup_codes: ["K7QF-92XM"] } });
    await expect(confirmTwoFactorSetup("482913")).resolves.toEqual(["K7QF-92XM"]);
    expect(api.post).toHaveBeenLastCalledWith("/v1/auth/two-factor/confirm/", { code: "482913" });
    vi.mocked(api.post).mockResolvedValueOnce({ data: undefined });
    await resetTwoFactor("u1", "Téléphone perdu");
    expect(api.post).toHaveBeenLastCalledWith("/v1/admin/droits/u1/two-factor/reset/", { motif: "Téléphone perdu" });
  });
});
