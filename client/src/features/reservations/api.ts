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
export async function withholdStayDeposit(id: string, withholding: { montant: number; motif: string; cgv_article: string; justificatifs: File[] }) {
  const body = new FormData();
  body.append("montant", String(withholding.montant));
  body.append("motif", withholding.motif);
  body.append("cgv_article", withholding.cgv_article);
  for (const f of withholding.justificatifs) body.append("justificatifs", f);
  return (await api.post<AdminStayDeposit>(`/v1/admin/reservations/${id}/caution/`, body)).data;
}

/** Cancellation by Kwa-Ba. From the double validation threshold, the refund waits for a second person: the answer
 * then carries `validation` and a message, and the booking stays as it is until it is approved. */
export async function annulerReservationAdmin(id: string, motif: string): Promise<{ attenteValidation: boolean; message: string }> {
  const res = await api.post<{ detail?: string; validation?: string }>(`/v1/admin/reservations/${id}/annuler/`, { motif });
  return { attenteValidation: res.status === 202, message: res.data?.detail ?? "Réservation annulée" };
}
