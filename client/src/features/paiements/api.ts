import api from "@/lib/api";
import type { ConfigPaiement, DevisSejour, MoyenPaiement, ProfilVersement, Revenus, StatutPaiementReservation } from "@/types/api/paiement";

const PAIEMENTS = "/v1/paiements";

export async function lireConfig() {
  return (await api.get<ConfigPaiement>(`${PAIEMENTS}/config/`)).data;
}

export async function lireDevis(hebergementId: string, params: Record<string, string | number>) {
  return (await api.get<DevisSejour>(`/v1/hebergements/${hebergementId}/devis/`, { params })).data;
}

/** Creates the FedaPay transaction: the answer gives the secure payment page. */
export async function demarrerPaiementReservation(reservationId: string, moyen?: MoyenPaiement) {
  return (await api.post<{ url: string }>(`${PAIEMENTS}/reservations/${reservationId}/payer/`, moyen ? { moyen } : {})).data.url;
}

export async function demarrerPaiementTransfert(transfertId: string, moyen: MoyenPaiement) {
  return (await api.post<{ url: string }>(`/v1/transferts/${transfertId}/payer/`, { moyen })).data.url;
}

export async function demarrerPaiementLocation(locationId: string, moyen: MoyenPaiement) {
  return (await api.post<{ url: string }>(`/v1/locations/${locationId}/payer/`, { moyen })).data.url;
}

export async function lireStatutReservation(reservationId: string) {
  return (await api.get<StatutPaiementReservation>(`${PAIEMENTS}/reservations/${reservationId}/statut/`)).data;
}

export const adresseCompteReservation = (reservationId: string) => `${PAIEMENTS}/reservations/${reservationId}/compte-remboursement/`;

/** `adresse`: the refund account of a stay, a transfer or a rental. */
export async function enregistrerCompteRemboursement(adresse: string, compte: { pays: string; operateur: string; numero: string }) {
  await api.put(adresse, compte);
}

export async function lireRevenus() {
  return (await api.get<Revenus>(`${PAIEMENTS}/revenus/`)).data;
}

export async function lireProfilVersement() {
  return (await api.get<ProfilVersement | null>(`${PAIEMENTS}/profil-versement/`)).data;
}

export async function enregistrerProfilVersement(profil: ProfilVersement) {
  return (await api.put<ProfilVersement>(`${PAIEMENTS}/profil-versement/`, profil)).data;
}

// --- Back-office: rates (AN-B1) and finances of a period (AN-B2)

export interface TarifsAdmin {
  /** In %: 6 means 6 % */
  taux: Record<"frais_voyageur" | "frais_reduits" | "commission_particulier" | "commission_hotel" | "commission_fondateur"
    | "commission_transfert", number>;
  /** FCFA per stay, by listing type */
  frais_menage: Record<string, number>;
  mis_a_jour_le: string | null;
  /** Other rates and delays of the referential (finance module), read only here (GL-20) */
  autres_taux?: { cle: string; libelle: string; valeur: string | number; unite: string; offre: string | null }[];
  /** Dated changes of the rates of this page */
  historique?: { cle: string; valeur_avant: string | number | null; valeur_apres: string | number; date_effet: string; motif: string | null }[];
}

export async function lireTarifsAdmin() {
  return (await api.get<TarifsAdmin>("/v1/admin/paiements/tarifs/")).data;
}

export async function modifierTarifsAdmin(tarifs: Pick<TarifsAdmin, "taux" | "frais_menage">) {
  return (await api.put<TarifsAdmin>("/v1/admin/paiements/tarifs/", tarifs)).data;
}

export interface VersementFinances {
  categorie: string; beneficiaire: string; objet: string; montant: number; commission: number; statut: string;
  date_prevue: string; envoye_le: string | null;
}

export interface Finances {
  debut: string;
  fin: string;
  totaux: { encaisse: number; nb_paiements: number; rembourse: number; rembourse_en_attente: number; verse: number;
    du_partenaires: number; revenu_kwaba: number };
  par_produit: Record<string, number>;
  par_prestataire: Record<string, number>;
  jours: { date: string; nb_paiements: number; encaisse: number; rembourse: number; verse: number; solde: number }[];
  versements: VersementFinances[];
}

export const URL_EXPORT_FINANCES = "/v1/admin/paiements/finances/";

export async function lireFinances(debut: string, fin: string) {
  return (await api.get<Finances>(URL_EXPORT_FINANCES, { params: { debut, fin } })).data;
}

// --- Back-office: refunds (GL-9) -------------------------------------------------------------------------------

export type StatutRemboursement = "attente_numero" | "a_envoyer" | "en_cours" | "envoye" | "a_traiter";
export type ActionRemboursement = "numero" | "relancer" | "manuel";

export interface RemboursementAdmin {
  id: string;
  montant: number;
  motif: string;
  statut: StatutRemboursement;
  statut_libelle: string;
  cree_le: string;
  envoye_le: string | null;
  derniere_erreur: string;
  tentatives: number;
  type_objet: string;
  objet_id: string;
  reference: string;
  payeur: string;
  paiement: { reference: string; montant: number; mode: string; carte: boolean };
  /** Mobile Money account, end of the number only */
  compte: string;
  actions: ActionRemboursement[];
}

export interface BaremeRemboursement {
  code: "voyageur" | "plateforme";
  libelle: string;
  montant: number;
  validation_requise: boolean;
}

export interface ApercuRemboursement {
  reservation: { id: string; reference: string; statut: string; voyageur: string; check_in: string; check_out: string; total: number };
  paye: number;
  /** Empty: never paid online, or already cancelled */
  baremes: BaremeRemboursement[];
  seuil: number;
  validation_en_attente: boolean;
}

const REMBOURSEMENTS = "/v1/admin/paiements/finances/remboursements/";

export async function lireRemboursements(statut: string, page: number) {
  return (await api.get<{ results: RemboursementAdmin[]; count: number; page: number; page_size: number }>(REMBOURSEMENTS, {
    params: { ...(statut ? { statut } : {}), page },
  })).data;
}

export async function lireApercuRemboursement(reference: string) {
  return (await api.get<ApercuRemboursement>(`${REMBOURSEMENTS}apercu/`, { params: { reference } })).data;
}

/** Cancels and refunds a paid stay; from the threshold it waits for a second person (202). */
export async function rembourserSejour(reservationId: string, bareme: BaremeRemboursement["code"], motif: string) {
  const res = await api.post<{ detail: string; validation?: string; rembourse?: number }>(`${REMBOURSEMENTS}sejour/`, {
    reservation_id: reservationId, bareme, motif,
  });
  return { attenteValidation: res.status === 202, message: res.data.detail };
}

export async function agirSurRemboursement(id: string, action: ActionRemboursement, corps: Record<string, string> = {}) {
  return (await api.post<RemboursementAdmin>(`${REMBOURSEMENTS}${id}/${action}/`, corps)).data;
}

// --- Payouts to the partners (GL-11) and recoveries after a cancellation (GL-23)

export type StatutVersementPartenaire = "planifie" | "en_cours" | "envoye" | "echoue" | "annule";

export interface VersementPartenaire {
  /** hote, or the paid product (transfert, location) */
  type: string;
  id: string;
  categorie: string;
  beneficiaire: string;
  objet: string;
  montant: number;
  /** Withheld for a recovery: `montant` is net of it */
  retenue: number;
  commission: number;
  statut: StatutVersementPartenaire;
  date_prevue: string;
  envoye_le: string | null;
  tentatives: number;
  derniere_erreur: string;
  en_retard: boolean;
  relancable: boolean;
}

export interface RecuperationHote {
  id: string;
  hote: string;
  objet: string;
  montant: number;
  recupere: number;
  reste: number;
  statut: "en_cours" | "soldee" | "annulee";
  motif: string;
  relances: number;
  derniere_relance_le: string | null;
  cree_le: string;
  versement_a_venir: boolean;
}

export interface VersementsPartenaires {
  versements: VersementPartenaire[];
  recuperations: RecuperationHote[];
  totaux: { du: number; en_retard: number; echoues: number; a_recuperer: number };
  retard_heures: number;
  peut_operer: boolean;
}

const VERSEMENTS = "/v1/admin/paiements/finances/versements/";

export async function lireVersementsPartenaires(statut: string) {
  return (await api.get<VersementsPartenaires>(VERSEMENTS, { params: statut ? { statut } : {} })).data;
}

export async function relancerVersement(type: string, id: string) {
  return (await api.post<{ detail: string }>(`${VERSEMENTS}${type}/${id}/relancer/`, {})).data;
}

export async function relancerRecuperation(id: string) {
  return (await api.post<{ detail: string; relances: number }>(`/v1/admin/paiements/finances/recuperations/${id}/relancer/`, {})).data;
}
