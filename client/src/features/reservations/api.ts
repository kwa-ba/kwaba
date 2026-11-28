import api from "@/lib/api";
import { urlProxy } from "@/lib/api-url";
import type { Paginated, Reservation } from "@/types/api/models";
import type { AdminReservationDetail, AdminStayDeposit } from "@/types/api/admin";

const RESERVATIONS = "/v1/reservations";

export async function listerMesReservations() {
  return (await api.get<Paginated<Reservation>>(`${RESERVATIONS}/`)).data.results;
}

export async function lireReservation(id: string) {
  return (await api.get<Reservation>(`${RESERVATIONS}/${id}/`)).data;
}

/** Address of the .ics file of a paid stay, opened by a plain link: the phone offers to add it to its calendar.
 * It goes through the site's proxy, which adds the session (no JavaScript download: the iPhone would not open it). */
export function lienCalendrier(id: string, langue: string) {
  return `${urlProxy(`${RESERVATIONS}/${encodeURIComponent(id)}/calendrier/`)}?langue=${langue === "en" ? "en" : "fr"}`;
}

export async function creerReservation(reservation: Record<string, unknown>) {
  return (await api.post<Reservation>(`${RESERVATIONS}/`, reservation)).data;
}

export async function annulerReservation(id: string) {
  return (await api.delete<{ rembourse?: number; numero_requis?: boolean }>(`${RESERVATIONS}/${id}/`)).data;
}

export async function lireReservationAdmin(id: string) {
  return (await api.get<AdminReservationDetail>(`/v1/admin/reservations/${id}/`)).data;
}

/** Withholding on the escrowed deposit of a stay for a damage (ADR-038): its reason, the article of the terms of sale
 * and the evidence, sent as multipart. 0 cancels it. */
export interface StayDepositAction {
  montant: number;
  motif: string;
  cgv_article?: string;
  justificatifs: File[];
}

async function postStayDeposit(id: string, chemin: string, action: StayDepositAction) {
  const body = new FormData();
  body.append("montant", String(action.montant));
  body.append("motif", action.motif);
  if (action.cgv_article !== undefined) body.append("cgv_article", action.cgv_article);
  for (const f of action.justificatifs) body.append("justificatifs", f);
  return (await api.post<AdminStayDeposit>(`/v1/admin/reservations/${id}/caution/${chemin}`, body)).data;
}

/** Amount the host claims for a damage (ADR-048): held while the team decides; 0 withdraws it. */
export const claimStayDeposit = (id: string, action: StayDepositAction) => postStayDeposit(id, "reclamation/", action);

/** The team's decision on the claim: the amount withheld, paid to the host after the contestation period. */
export const decideStayDeposit = (id: string, action: StayDepositAction) => postStayDeposit(id, "", action);

/** Cancellation by Kwa-Ba. From the double validation threshold, the refund waits for a second person: the answer
 * then carries `validation` and a message, and the booking stays as it is until it is approved. */
export async function annulerReservationAdmin(id: string, motif: string): Promise<{ attenteValidation: boolean; message: string }> {
  const res = await api.post<{ detail?: string; validation?: string }>(`/v1/admin/reservations/${id}/annuler/`, { motif });
  return { attenteValidation: res.status === 202, message: res.data?.detail ?? "Réservation annulée" };
}
