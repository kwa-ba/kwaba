import api from "@/lib/api";
import type { Gamme, GammeAdmin } from "./types";

const ADMIN = "/admin/mobilite";

/** The active ranges (all, or those offered in transfer / in rental). */
export async function listerGammes(usage?: "transfert" | "location") {
  return (await api.get<Gamme[]>("/mobilite/gammes/", { params: usage ? { usage } : {} })).data;
}

export async function listerGammesAdmin() {
  return (await api.get<GammeAdmin[]>(`${ADMIN}/gammes/`)).data;
}

export async function creerGamme(gamme: Partial<GammeAdmin>) {
  return (await api.post<GammeAdmin>(`${ADMIN}/gammes/`, gamme)).data;
}

export async function modifierGamme(code: string, gamme: Partial<GammeAdmin>) {
  return (await api.patch<GammeAdmin>(`${ADMIN}/gammes/${code}/`, gamme)).data;
}
