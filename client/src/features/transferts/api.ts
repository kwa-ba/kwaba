import api from "@/lib/api";
import type { AeroportAdmin, ChauffeurAdmin } from "@/types/api/admin";
import type { Paginated } from "@/types/api/models";
import type { Aeroport, Devis, Transfert } from "./types";

const TRANSFERTS = "/v1/transferts";
const ADMIN = "/v1/admin/transferts";

export async function listerMesTransferts() {
  return (await api.get<Paginated<Transfert>>(`${TRANSFERTS}/`)).data.results;
}

export async function lireTransfert(id: string) {
  return (await api.get<Transfert>(`${TRANSFERTS}/${id}/`)).data;
}

export async function listerAeroports() {
  return (await api.get<Aeroport[]>(`${TRANSFERTS}/aeroports/`)).data;
}

export async function calculerDevis(params: { aeroport: string; arrivee: string; passagers: number; bagages: number }) {
  return (await api.get<Devis>(`${TRANSFERTS}/devis/`, { params })).data;
}

export async function creerTransfert(transfert: Record<string, unknown>) {
  return (await api.post<Transfert>(`${TRANSFERTS}/`, transfert)).data;
}

export async function annulerTransfert(id: string) {
  return (await api.delete<{ rembourse: number; numero_requis: boolean }>(`${TRANSFERTS}/${id}/`)).data;
}

export const adresseCompteRemboursement = (id: string) => `${TRANSFERTS}/${id}/compte-remboursement/`;

export async function listerAeroportsAdmin() {
  return (await api.get<AeroportAdmin[]>(`${ADMIN}/aeroports/`)).data;
}

export async function creerAeroport(aeroport: unknown) {
  return (await api.post<AeroportAdmin>(`${ADMIN}/aeroports/`, aeroport)).data;
}

export async function modifierAeroport(code: string, aeroport: unknown) {
  await api.patch(`${ADMIN}/aeroports/${code}/`, aeroport);
}

export async function enregistrerTarifs(code: string, tarifs: unknown[]) {
  await api.put(`${ADMIN}/aeroports/${code}/tarifs/`, tarifs);
}

export async function listerChauffeurs() {
  return (await api.get<ChauffeurAdmin[]>(`${ADMIN}/chauffeurs/`)).data;
}

export async function creerChauffeur(chauffeur: unknown) {
  await api.post(`${ADMIN}/chauffeurs/`, chauffeur);
}

export async function modifierChauffeur(id: ChauffeurAdmin["id"], chauffeur: unknown) {
  await api.patch(`${ADMIN}/chauffeurs/${id}/`, chauffeur);
}

/** The driver owns the car they drive: it becomes their vehicle record (T-H2). Returns the updated driver. */
export async function creerVehiculeChauffeur(id: ChauffeurAdmin["id"]) {
  return (await api.post<ChauffeurAdmin>(`${ADMIN}/chauffeurs/${id}/vehicule/`, {})).data;
}

export async function listerChauffeursDisponibles(transfertId: string) {
  return (await api.get<{ id: number; nom: string; telephone: string; vehicule: string }[]>(`${ADMIN}/transferts/${transfertId}/chauffeurs/`)).data;
}

export async function attribuerChauffeur(transfertId: string, chauffeur: number) {
  await api.post(`${ADMIN}/transferts/${transfertId}/attribuer/`, { chauffeur });
}

export async function annulerTransfertAdmin(transfertId: string, motif: string) {
  await api.post(`${ADMIN}/transferts/${transfertId}/annuler/`, { motif });
}

export async function noterChauffeurTransfert(id: string, avis: unknown) {
  return (await api.post(`${TRANSFERTS}/${id}/avis-chauffeur/`, avis)).data;
}

// --- Back-office: photo, levels, incidents and ratings of the drivers

export interface LigneRevueNiveaux {
  chauffeur_id: number;
  nom: string;
  niveau: "standard" | "excellence";
  propose: "standard" | "excellence";
  photo_validee: boolean;
  /** Founders Programme in force: Excellence from `courses_requises` missions (10 instead of 20) */
  fondateur: boolean;
  courses_requises: number;
  chiffres: {
    courses: number; avis: number; note: number | string | null;
    graves: number; retards: number; absences: number; plaintes: number; accidents: number;
  };
}

export type TypeIncident = "grave" | "retard" | "absence" | "plainte" | "accident" | "autre";

export interface RevueNiveaux {
  depuis: string;
  seuils: Record<string, number>;
  libelles: Record<string, string>;
  chauffeurs: LigneRevueNiveaux[];
}

export interface SuiviChauffeur {
  avis: { objet_type: string; note: number; ponctualite: number; conduite: number; amabilite: number; commentaire: string; cree_le: string }[];
  incidents: { id: number; type: TypeIncident; date: string; description: string; reference: string }[];
  niveaux: { avant: string; apres: string; propose: string; motif: string; le: string }[];
}

export async function envoyerPhotoChauffeur(id: number, image: File) {
  const corps = new FormData();
  corps.append("image", image);
  return (await api.post(`${ADMIN}/chauffeurs/${id}/photo/`, corps)).data;
}

export async function validerPhotoChauffeur(id: number) {
  return (await api.post(`${ADMIN}/chauffeurs/${id}/photo/valider/`, {})).data;
}

export async function lireRevueNiveaux() {
  return (await api.get<RevueNiveaux>(`${ADMIN}/chauffeurs/niveaux/`)).data;
}

export async function validerNiveau(chauffeur: number, niveau: string, motif = "") {
  return (await api.post(`${ADMIN}/chauffeurs/niveaux/`, { chauffeur, niveau, motif })).data;
}

export async function lireSuiviChauffeur(id: number) {
  return (await api.get<SuiviChauffeur>(`${ADMIN}/chauffeurs/${id}/suivi/`)).data;
}

export async function signalerIncident(id: number, incident: { type: string; date: string; description: string; reference: string }) {
  return (await api.post(`${ADMIN}/chauffeurs/${id}/suivi/`, incident)).data;
}
