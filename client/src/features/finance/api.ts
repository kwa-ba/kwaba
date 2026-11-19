import api from "@/lib/api";

// --- Back-office: the ledger of money movements (module finance, ADR-024)

export interface InvariantFinance {
  invariant: string;
  libelle: string;
  /** 0: the invariant holds */
  anomalies: number;
}

export interface DuPartenaire {
  tiers_type: string;
  tiers_id: string | null;
  /** Empty for a third party that is not an account (driver, rental partner) */
  nom: string;
  email: string;
  solde_du: number;
}

export interface MouvementFinance {
  id: number;
  date_evenement: string;
  famille: string;
  nature_code: string;
  nature_libelle: string;
  offre_code: string;
  tiers_type: string | null;
  tiers_id: string | null;
  nom: string;
  email: string;
  compte_argent_code: string;
  moyen_paiement_code: string | null;
  piece_reference: string | null;
  montant: number;
  /** Positive: money in; negative: money out */
  montant_signe: number;
  origine: string;
  annule_mouvement_id: number | null;
}

export interface GrandLivre {
  invariants: InvariantFinance[];
  soldes: {
    revenu_du_mois: number;
    du_partenaires: number;
    du_voyageurs: number;
    cautions_detenues: number;
    comptes: Record<string, number>;
  };
  du_aux_partenaires: DuPartenaire[];
  mouvements: MouvementFinance[];
}

export async function lireGrandLivre() {
  return (await api.get<GrandLivre>("/v1/admin/finance/grand-livre/")).data;
}

// --- Books of article 19, closing, reports (GL-2 to GL-7, GL-19) ---------------------------------------------------

/** Paginated list of the back-office (documentation/modules/backoffice-api.md). */
export interface PageFinance<T> {
  results: T[];
  count: number;
  page: number;
  page_size: number;
}

export interface CodeLibelle {
  code: string;
  libelle: string;
}

export interface Referentiels {
  familles: CodeLibelle[];
  natures: (CodeLibelle & { famille: string; actif: boolean })[];
  offres: (CodeLibelle & { active: boolean })[];
  tiers_types: CodeLibelle[];
  comptes_argent: (CodeLibelle & { actif: boolean })[];
  journaux: CodeLibelle[];
}

export interface FiltresMouvements {
  du?: string;
  au?: string;
  nature?: string;
  famille?: string;
  offre?: string;
  tiers_type?: string;
  tiers_id?: string;
  compte_argent?: string;
  piece?: string;
  sens?: "" | "entree" | "sortie";
}

export interface LigneMouvement extends MouvementFinance {
  motif: string | null;
}

export interface EcritureJournal {
  date_ecriture: string;
  journal: string;
  mouvement_id: number;
  ligne_ecriture: number;
  compte_general: string;
  compte_auxiliaire: string | null;
  piece: string | null;
  libelle: string;
  debit: number;
  credit: number;
  devise: string;
}

export interface Totaux {
  total_debit: number;
  total_credit: number;
}

export interface CompteGeneral {
  compte_general: string;
  libelle: string;
  nb_lignes: number;
  /** Debit minus credit, from the first entry */
  solde: number;
}

export interface CompteAuxiliaire {
  compte_auxiliaire: string;
  nb_lignes: number;
  solde: number;
  nom: string;
  email: string;
}

export interface EcritureCompte extends Omit<EcritureJournal, "devise"> {
  solde_progressif: number;
}

export interface GrandLivreCompte extends PageFinance<EcritureCompte>, Totaux {
  solde_ouverture: number;
  solde_cloture: number;
}

export interface LigneBalance extends Totaux {
  compte_general: string;
  libelle: string;
  solde_ouverture: number;
  solde_cloture: number;
}

export interface Balance {
  comptes: LigneBalance[];
  totaux: Totaux;
  equilibree: boolean;
}

export interface Pilotage {
  mois: string;
  marge_par_offre: { offre_code: string; recettes: number; charges_variables: number; marge: number }[];
  taux_frais_reel: { frais: number; revenu: number; volume_encaisse: number; pct_du_revenu: number | null } | null;
  fonds_garantie: number;
}

export type EtatMois = "ouverte" | "en_controle" | "verrouillee";

export interface MoisComptable {
  mois: string;
  etat: EtatMois;
  verrouillee_le: string | null;
  en_cours: boolean;
}

export interface ControleCloture {
  controle: string;
  resultat: string;
  verdict: "OK" | "REFUSE";
  que_faire: string;
}

export interface Rapport {
  code: string;
  titre: string;
  axe1: string;
  axe2: string | null;
  familles: string[] | null;
  offres: string[] | null;
  periodicite: string | null;
  destinataire: string | null;
}

export interface DemandeRapport {
  /** A saved report, or the axes and filters of a free one */
  code?: string;
  axe1?: string;
  axe2?: string;
  familles?: string[];
  offres?: string[];
}

export interface ResultatRapport {
  titre: string;
  lignes: { axe1: string | null; axe2: string | null; nb: number; montant: number }[];
  total: number;
}

export interface NouveauRapport {
  code: string;
  titre: string;
  axe1: string;
  axe2?: string | null;
  familles?: string[];
  offres?: string[];
}

const FINANCE = "/v1/admin/finance";

/** Query string without the empty values. */
export function parametres(valeurs: Record<string, string | number | string[] | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(valeurs)) {
    if (valeur === undefined || valeur === null || valeur === "") continue;
    if (Array.isArray(valeur)) {
      if (valeur.length) q.set(cle, valeur.join(","));
    } else {
      q.set(cle, String(valeur));
    }
  }
  const texte = q.toString();
  return texte ? `?${texte}` : "";
}

export async function lireReferentiels() {
  return (await api.get<Referentiels>(`${FINANCE}/referentiels/`)).data;
}

export async function lireMouvements(filtres: FiltresMouvements, page: number, pageSize = 20) {
  return (await api.get<PageFinance<LigneMouvement>>(`${FINANCE}/mouvements/${parametres({ ...filtres, page, page_size: pageSize })}`)).data;
}

export async function lireLivreJournal(debut: string, fin: string, journal: string, page: number, pageSize = 50) {
  return (await api.get<PageFinance<EcritureJournal> & { totaux: Totaux }>(
    `${FINANCE}/livre-journal/${parametres({ debut, fin, journal, page, page_size: pageSize })}`)).data;
}

export async function lireComptes() {
  return (await api.get<CompteGeneral[]>(`${FINANCE}/comptes/`)).data;
}

export async function lireAuxiliaires(compte: string) {
  return (await api.get<CompteAuxiliaire[]>(`${FINANCE}/comptes/${encodeURIComponent(compte)}/auxiliaires/`)).data;
}

export async function lireGrandLivreCompte(compte: string, auxiliaire: string, debut: string, fin: string, page: number, pageSize = 50) {
  return (await api.get<GrandLivreCompte>(
    `${FINANCE}/grand-livre-compte/${parametres({ compte, auxiliaire, debut, fin, page, page_size: pageSize })}`)).data;
}

export async function lireBalance(debut: string, fin: string) {
  return (await api.get<Balance>(`${FINANCE}/balance/${parametres({ debut, fin })}`)).data;
}

export async function lirePilotage(mois: string) {
  return (await api.get<Pilotage>(`${FINANCE}/pilotage/${parametres({ mois })}`)).data;
}

/** Address of the accounting file (CSV) for a download. */
export function urlExportEcritures(debut: string, fin: string) {
  return `${FINANCE}/export/ecritures/${parametres({ debut, fin })}`;
}

export async function lireMoisComptables() {
  return (await api.get<{ mois: MoisComptable[]; peut_verrouiller: boolean }>(`${FINANCE}/cloture/`)).data;
}

/** `mois`: « 2026-10 » */
export async function lireControlesCloture(mois: string) {
  return (await api.get<{ mois: string; controles: ControleCloture[] }>(`${FINANCE}/cloture/${mois}/`)).data;
}

/** Locks a month for good; `confirmation` is the month typed as « 10/2026 ». */
export async function cloturerMois(mois: string, confirmation: string) {
  return (await api.post<{ mois: string; controles: ControleCloture[] }>(`${FINANCE}/cloture/${mois}/`, { confirmation })).data;
}

export async function lireRapports() {
  return (await api.get<{ rapports: Rapport[]; axes: CodeLibelle[] }>(`${FINANCE}/rapports/`)).data;
}

export async function lireResultatRapport(demande: DemandeRapport, debut: string, fin: string) {
  return (await api.get<ResultatRapport>(`${FINANCE}/rapports/resultat/${parametres({ ...demande, debut, fin })}`)).data;
}

export function urlExportRapport(demande: DemandeRapport, debut: string, fin: string) {
  return `${FINANCE}/rapports/export/${parametres({ ...demande, debut, fin })}`;
}

export async function creerRapport(rapport: NouveauRapport) {
  return (await api.post<Rapport>(`${FINANCE}/rapports/`, rapport)).data;
}

// --- Double validation (GL-10) ---------------------------------------------------------------------------------

export type StatutValidation = "en_attente" | "executee" | "refusee" | "echouee";

export interface ValidationFinance {
  id: string;
  operation: string;
  operation_libelle: string;
  objet_type: string;
  objet_id: string;
  montant: number;
  motif: string;
  donnees: Record<string, string>;
  statut: StatutValidation;
  /** « Système » when the worker asked (a payout due): two approvals are then needed */
  demandee_par: string;
  demandee_le: string;
  premiere_par: string;
  decidee_par: string;
  decidee_le: string | null;
  resultat: string;
  je_peux_valider: boolean;
}

export async function lireValidations(statut: string) {
  return (await api.get<{ seuil: number; peut_operer: boolean; validations: ValidationFinance[] }>(
    `${FINANCE}/validations/${parametres({ statut })}`)).data;
}

export async function deciderValidation(id: string, decision: "approuver" | "refuser", motif = "") {
  return (await api.post<ValidationFinance>(`${FINANCE}/validations/${id}/${decision}/`, decision === "refuser" ? { motif } : {})).data;
}

// --- Register of the deposits (GL-13, GL-14) -----------------------------------------------------------------------

export type StatutCaution = "detenue" | "restituee" | "retenue";

export interface CautionFinance {
  objet_type: string;
  objet_id: string;
  reference: string;
  offre: string;
  voyageur: string;
  montant: number;
  recue_le: string;
  date_limite: string;
  statut: StatutCaution;
  montant_retenu: number;
  montant_rendu: number;
  motif_retenue: string;
  cgv_article: string;
  decision_par: string;
  decision_le: string | null;
  soldee_le: string | null;
  mode_restitution: string;
  /** REC receipt or RET notice, once settled */
  document_numero: string;
  en_retard: boolean;
}

export interface Justificatif {
  id: string;
  nom: string;
  taille: number;
  ajoute_le: string;
}

export async function lireCautions(statut: string, retard: boolean) {
  return (await api.get<{ cautions: CautionFinance[]; total_detenu: number; en_retard: number }>(
    `${FINANCE}/cautions/${parametres({ statut, retard: retard ? "1" : "" })}`)).data;
}

/** PDF of a REC receipt or RET notice, by its number. */
export function urlDocumentCaution(numero: string) {
  return `/v1/admin/documents/cautions/${encodeURIComponent(numero)}/pdf/`;
}

export async function lireJustificatifs(objetType: string, objetId: string) {
  return (await api.get<Justificatif[]>(`/v1/admin/documents/justificatifs/${parametres({ objet_type: objetType, objet_id: objetId })}`)).data;
}

export function urlJustificatif(id: string) {
  return `/v1/admin/documents/justificatifs/${id}/`;
}
