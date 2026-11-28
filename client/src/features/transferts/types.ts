import type { MoyenPaiement, StatutPaiement } from "@/types/api/paiement";

export interface Aeroport {
  code: string;
  nom: string;
  ville: string;
  pays: string;
  fuseau: string;
  /** Price of each vehicle from this airport (same price by day and by night). */
  prix: Partial<Record<CategorieVehicule, number>>;
}

/** A range of the mobility referential offered in transfer (berline, suv, minibus… : T-H1). */
export type CategorieVehicule = string;

// Former transfer codes (before 28 November 2026), still in a draft kept by the browser
const ANCIENS_CODES: Record<string, string> = { confort: "suv", van: "minibus" };

export function normaliserGamme(code: string): CategorieVehicule {
  return ANCIENS_CODES[code] ?? code;
}

export interface Vehicule {
  nom: string;
  description: string;
  passagers: number;
  bagages: number;
}

export interface OptionDevis extends Vehicule {
  categorie: CategorieVehicule;
  prix: number;
  disponible: boolean;
  motif: string;
}

export interface Devis {
  options: OptionDevis[];
  trop_tard: boolean;
  delai_min_heures: number;
  attente_incluse_minutes: number;
}

export type StatutTransfert = "en_attente_paiement" | "confirme" | "chauffeur_assigne" | "termine" | "annule";

export interface Transfert {
  id: string;
  reference: string;
  aeroport: string;
  aeroport_detail: Aeroport;
  arrivee: string;
  /** Ticket time, in the airport's time zone (YYYY-MM-DDTHH:MM). */
  arrivee_locale: string;
  numero_vol: string;
  passagers: number;
  bagages: number;
  categorie: CategorieVehicule;
  vehicule: Vehicule;
  destination: string;
  telephone: string;
  message: string;
  reservation: string | null;
  prix: number;
  majoration_nuit: boolean;
  moyen: MoyenPaiement;
  statut: StatutTransfert;
  expire_le: string | null;
  annule_par: "" | "voyageur" | "plateforme" | "expiration";
  chauffeur: {
    nom: string; telephone: string; vehicule: string; immatriculation: string;
    /** Level of the driver, and their photo validated by the team (to recognise them at arrivals) */
    niveau: NiveauChauffeur; niveau_libelle: string; photo: string | null;
  } | null;
  /** A ride done: the traveller may rate the driver once */
  avis_chauffeur: { donne: boolean } | null;
  paiement: StatutPaiement | null;
  remboursement: { montant: number; statut: "attente_numero" | "en_cours" | "envoye" } | null;
  annulation_gratuite: boolean;
  cree_le: string;
}

export type NiveauChauffeur = "standard" | "excellence";
