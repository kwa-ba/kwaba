import api, { estErreurApi } from "@/lib/api";
import type { AdminStats, AdminUser, DroitsAdmin, TwoFactorSetup, TwoFactorStatus } from "@/types/api/admin";
import type { Me } from "@/types/api/models";

const MOI = "/v1/users/me/";

export async function lireMoi() {
  return (await api.get<Me>(MOI)).data;
}

export async function modifierMoi(champs: Partial<Pick<Me, "first_name" | "last_name" | "phone">>) {
  return (await api.patch<Me>(MOI, champs)).data;
}

/** The role does not change: the account becomes a host once an agent has validated a first listing. */
export async function ouvrirCandidature() {
  return (await api.post<Me>(`${MOI}candidature/`)).data;
}

/** Emails a code confirming the deletion of the account (ADR-039). Refused (409) while something is still pending. */
export async function requestAccountDeletionCode() {
  await api.post(`${MOI}deletion-code/`);
}

/** Deletes the account for good, with the emailed code. */
export async function deleteMyAccount(code: string) {
  await api.delete(MOI, { data: { code } });
}

/** What must end before the account can be deleted (an upcoming stay, a payout to receive…). */
export type AccountDeletionBlocker = { code: string; detail: string };

export function accountDeletionBlockers(err: unknown): AccountDeletionBlocker[] {
  if (!estErreurApi(err) || err.response?.status !== 409) return [];
  const blockers = (err.response.data as { blockers?: AccountDeletionBlocker[] } | undefined)?.blockers;
  return Array.isArray(blockers) ? blockers : [];
}

export async function modifierUtilisateurAdmin(id: AdminUser["id"], champs: Record<string, unknown>) {
  await api.patch(`/v1/admin/users/${id}/`, champs);
}

export async function lireDroitsAdmin() {
  return (await api.get<DroitsAdmin>("/v1/admin/droits/")).data;
}

export async function lireStatsAdmin() {
  return (await api.get<AdminStats>("/v1/admin/stats/")).data;
}

const TWO_FACTOR = "/v1/auth/two-factor/";

export async function readTwoFactorStatus() {
  return (await api.get<TwoFactorStatus>(TWO_FACTOR)).data;
}

/** New pending secret, shown as a QR code and as a key to type. */
export async function startTwoFactorSetup() {
  return (await api.post<TwoFactorSetup>(`${TWO_FACTOR}setup/`)).data;
}

/** First right code: the second factor becomes active. Returns the backup codes, shown only once. */
export async function confirmTwoFactorSetup(code: string) {
  return (await api.post<{ backup_codes: string[] }>(`${TWO_FACTOR}confirm/`, { code })).data.backup_codes;
}

/** Super admin: removes another admin's second factor (lost phone), with a reason. */
export async function resetTwoFactor(id: AdminUser["id"], motif: string) {
  await api.post(`/v1/admin/droits/${id}/two-factor/reset/`, { motif });
}
