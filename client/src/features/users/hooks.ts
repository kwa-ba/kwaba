import { useQuery } from "@tanstack/react-query";
import { lireDroitsAdmin, lireMoi, readTwoFactorStatus } from "./api";
import type { Me } from "@/types/api/models";

export const CLE_MOI = ["me"];

export function useMoi(enabled = true) {
  return useQuery({ queryKey: CLE_MOI, queryFn: lireMoi, enabled });
}

/** What the signed-in admin can do. Display only: the API checks every request on its own. */
export function useDroitsAdmin(enabled = true) {
  return useQuery({ queryKey: ["admin", "droits"], queryFn: lireDroitsAdmin, enabled });
}

export const TWO_FACTOR_KEY = ["two-factor"];

/** Second factor of the signed-in admin. Its own key: invalidating ["admin"] after an edit does not read it again. */
export function useTwoFactorStatus(enabled = true) {
  return useQuery({ queryKey: TWO_FACTOR_KEY, queryFn: readTwoFactorStatus, enabled, retry: false, staleTime: 60_000 });
}

/** Host, administrator or candidate: may open the host space and prepare listings (same rule as the API).
 *  Read from the profile, not the session: the role changes on the server when an agent validates a listing. */
export function accesEspaceHote(moi: Pick<Me, "role" | "candidature_hote">) {
  return moi.role === "hote" || moi.role === "admin" || moi.candidature_hote === "ouverte";
}
