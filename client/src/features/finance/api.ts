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

// --- Reconciliation with FedaPay (GL-12) ---------------------------------------------------------------------------

export type EtatRapprochement = "fait" | "en_erreur" | "non_fait";
export type EtatOperation = "concorde" | "ecart" | "regularisee" | "hors_livre";

export interface JourRapprochement {
  jour: string;
  etat: EtatRapprochement;
  ecart: number | null;
  calcule_le: string | null;
  message: string | null;
  solde_kwaba?: number;
  solde_livre?: number | null;
  solde_externe?: number | null;
  frais?: number;
  hors_grand_livre?: number;
  internes?: number;
  nb_operations?: number;
  nb_anomalies?: number;
}

export interface MoisRapprochement {
  compte_argent: string;
  mois: string;
  jours: JourRapprochement[];
  resume: Record<EtatRapprochement, number>;
  peut_importer: boolean;
  peut_regulariser: boolean;
  seuil_double_validation: number;
  /** Accounts reconciled: FedaPay, and the bank once open (GL-22) */
  comptes?: { code: string; libelle: string }[];
}

export interface OperationRapprochee {
  reference: string;
  type: "encaissement" | "remboursement" | "versement" | "inconnu";
  sens: "entree" | "sortie";
  date_operation: string | null;
  kwaba_reference: string;
  kwaba_montant: number | null;
  kwaba_statut: string;
  externe_montant: number | null;
  externe_frais: number | null;
  externe_statut: string;
  moyen_paiement_code: string | null;
  hors_grand_livre: boolean;
  offre_code: string | null;
  livre_montant: number;
  etat: EtatOperation;
  message: string;
}

export interface RegularisationFinance {
  id: string;
  jour: string;
  reference: string;
  nature: string;
  offre: string;
  sens: "entree" | "sortie";
  montant: number;
  motif: string;
  statut: "en_attente" | "ecrite" | "refusee";
  demandee_par: string;
  demandee_le: string;
  mouvement_id: number | null;
}

export interface DetailRapprochement {
  jour: JourRapprochement;
  operations: OperationRapprochee[];
  regularisations: RegularisationFinance[];
}

export interface NouvelleRegularisation {
  reference: string;
  nature: string;
  offre: string;
  sens: "entree" | "sortie";
  montant: number;
  motif: string;
  fichiers: File[];
}

export async function lireRapprochements(mois: string, compte = "FEDAPAY") {
  return (await api.get<MoisRapprochement>(`${FINANCE}/rapprochement/${parametres({ mois: mois.slice(0, 7), compte })}`)).data;
}

export async function lireRapprochementJour(jour: string, compte = "FEDAPAY") {
  return (await api.get<DetailRapprochement>(`${FINANCE}/rapprochement/${jour}/${parametres({ compte })}`)).data;
}

/** Reads FedaPay again for these finished days (31 at most) and reconciles each one. */
export async function importerRapprochement(debut: string, fin: string) {
  return (await api.post<{ jours: (JourRapprochement & { remarque?: string })[] }>(
    "/v1/admin/paiements/rapprochement/importer/", { debut, fin })).data;
}

export async function regulariserRapprochement(jour: string, r: NouvelleRegularisation, compte = "FEDAPAY") {
  const corps = new FormData();
  corps.append("reference", r.reference);
  corps.append("nature", r.nature);
  corps.append("offre", r.offre);
  corps.append("sens", r.sens);
  corps.append("montant", String(r.montant));
  corps.append("motif", r.motif);
  for (const f of r.fichiers) corps.append("fichiers", f);
  return (await api.post<RegularisationFinance & { attente_validation: boolean }>(
    `${FINANCE}/rapprochement/${jour}/regulariser/${parametres({ compte })}`, corps)).data;
}

// --- Expenses, suppliers and associates (GL-15) --------------------------------------------------------------------

export type StatutDepense = "en_attente" | "ecrite" | "refusee" | "annulee";

export interface DepenseFinance {
  id: string;
  numero: string;
  date_depense: string;
  nature: string;
  offre: string;
  montant: number;
  libelle: string;
  fournisseur_id: string;
  fournisseur: string;
  associe_id: string | null;
  associe: string;
  reference_facture: string;
  statut: StatutDepense;
  demandee_par: string;
  demandee_le: string;
  ecrite_le: string | null;
  annulee_le: string | null;
  motif_annulation: string;
}

export interface ListeDepenses extends PageFinance<DepenseFinance> {
  montant_ecrit: number;
  seuil: number;
  peut_saisir: boolean;
}

export interface FiltresDepenses {
  debut?: string;
  fin?: string;
  nature?: string;
  fournisseur?: string;
  associe?: string;
  statut?: string;
}

export interface NouvelleDepense {
  date_depense: string;
  nature: string;
  offre: string;
  montant: number;
  libelle: string;
  fournisseur: string;
  associe: string;
  reference_facture: string;
  fichiers: File[];
}

export interface FournisseurFinance {
  id: string;
  nom: string;
  nif: string;
  contact: string;
  actif: boolean;
}

export interface AssocieFinance {
  id: string;
  nom: string;
  email: string;
  compte_id: string | null;
  actif: boolean;
  /** Part of the share capital, F CFA (GL-16) */
  capital_souscrit: number;
}

export async function lireDepenses(filtres: FiltresDepenses, page: number, pageSize = 20) {
  return (await api.get<ListeDepenses>(`${FINANCE}/depenses/${parametres({ ...filtres, page, page_size: pageSize })}`)).data;
}

/** An expense with its evidence (multipart): written at once, or waiting for a second person from the threshold. */
export async function saisirDepense(d: NouvelleDepense) {
  const corps = new FormData();
  for (const cle of ["date_depense", "nature", "offre", "libelle", "fournisseur", "associe", "reference_facture"] as const) {
    corps.append(cle, d[cle]);
  }
  corps.append("montant", String(d.montant));
  for (const f of d.fichiers) corps.append("fichiers", f);
  return (await api.post<DepenseFinance & { attente_validation: boolean }>(`${FINANCE}/depenses/`, corps)).data;
}

export async function annulerDepense(id: string, motif: string) {
  return (await api.post<DepenseFinance>(`${FINANCE}/depenses/${id}/annuler/`, { motif })).data;
}

export async function lireFournisseurs() {
  return (await api.get<FournisseurFinance[]>(`${FINANCE}/fournisseurs/`)).data;
}

export async function enregistrerFournisseur(f: Partial<FournisseurFinance> & { nom: string }) {
  const { id, ...champs } = f;
  return (id ? await api.patch<FournisseurFinance>(`${FINANCE}/fournisseurs/${id}/`, champs)
    : await api.post<FournisseurFinance>(`${FINANCE}/fournisseurs/`, champs)).data;
}

export async function lireAssocies() {
  return (await api.get<AssocieFinance[]>(`${FINANCE}/associes/`)).data;
}

export async function enregistrerAssocie(a: Partial<AssocieFinance> & { nom: string }) {
  const { id, ...champs } = a;
  return (id ? await api.patch<AssocieFinance>(`${FINANCE}/associes/${id}/`, champs)
    : await api.post<AssocieFinance>(`${FINANCE}/associes/`, champs)).data;
}

// --- Associates' current accounts (GL-16)

export interface CompteCourantAssocie extends AssocieFinance {
  /** Advances and expenses they paid (F02, F03) */
  avances: number;
  /** Paid back to them (F04) */
  remboursements: number;
  /** What Kwa-Ba owes them: never below zero */
  solde: number;
}

export interface ComptesCourants {
  associes: CompteCourantAssocie[];
  totaux: { avances: number; remboursements: number; solde: number };
  capital_social: number;
  capital_souscrit: number;
  peut_modifier: boolean;
  remboursements_ouverts: boolean;
}

export interface LigneCompteCourant {
  mouvement_id: number;
  date: string;
  piece: string | null;
  nature: string;
  nature_libelle: string;
  libelle: string;
  montant_signe: number;
  annule_mouvement_id: number | null;
  solde: number;
}

export async function lireComptesCourants() {
  return (await api.get<ComptesCourants>(`${FINANCE}/associes/comptes/`)).data;
}

export async function lireReleveAssocie(id: string) {
  return (await api.get<{ associe: AssocieFinance; lignes: LigneCompteCourant[]; solde: number }>(
    `${FINANCE}/associes/${id}/releve/`)).data;
}

// --- Guarantee fund (GL-17)

export interface DotationFonds {
  mois: string;
  /** Net revenue of the month (family R) */
  assiette: number;
  taux: number | string;
  due: number;
  ecrite: number;
  etat: string;
  termine: boolean;
}

export interface SinistreFonds {
  id: string;
  depense_id: string;
  montant: number;
  decision_reference: string;
  motif: string;
  statut: "impute" | "annule";
  impute_par: string;
  impute_le: string;
  annule_le: string | null;
  motif_annulation: string;
  depense: { numero: string; libelle: string; date_depense: string; montant: number; offre: string };
}

export interface PochesTresorerie {
  tresorerie: number;
  du_partenaires: number;
  du_voyageurs: number;
  cautions_detenues: number;
  fonds_garantie: number;
  libre: number;
}

export interface FondsGarantie {
  solde: number;
  cible: number;
  sous_cible: boolean;
  taux: number | string;
  poches: PochesTresorerie;
  dotations: DotationFonds[];
  sinistres: SinistreFonds[];
  depenses_a_couvrir: DepenseFinance[];
  peut_operer: boolean;
}

export interface NouveauSinistre {
  depense: string;
  montant: number;
  decision_reference: string;
  motif: string;
}

export async function lireFondsGarantie() {
  return (await api.get<FondsGarantie>(`${FINANCE}/fonds-garantie/`)).data;
}

/** Writes what the allocation of a finished month lacks (every finished open month without `mois`). */
export async function doterFondsGarantie(mois?: string) {
  return (await api.post<{ dotations: DotationFonds[]; ajoute: number }>(`${FINANCE}/fonds-garantie/doter/`,
    mois ? { mois: mois.slice(0, 7) } : {})).data;
}

export async function imputerSinistre(s: NouveauSinistre) {
  return (await api.post<SinistreFonds>(`${FINANCE}/fonds-garantie/sinistres/`, s)).data;
}

export async function annulerSinistre(id: string, motif: string) {
  return (await api.post<SinistreFonds>(`${FINANCE}/fonds-garantie/sinistres/${id}/annuler/`, { motif })).data;
}

// --- Steered parameters and their history (GL-20)

export interface ParametreFinance {
  cle: string;
  valeur: string | number;
  unite: string;
  categorie: string;
  offre: string | null;
  libelle: string;
  source: string | null;
  actif: boolean;
  maj_le: string | null;
  /** Set from the Tarifs page (the site reads it at every booking) */
  page_tarifs: boolean;
}

export interface ChangementParametre {
  cle: string;
  valeur_avant: string | number | null;
  valeur_apres: string | number;
  date_effet: string;
  motif: string | null;
  par: string;
}

export async function lireParametres() {
  return (await api.get<{ parametres: ParametreFinance[]; historique: ChangementParametre[]; peut_modifier: boolean }>(
    `${FINANCE}/parametres/`)).data;
}

export async function lireHistoriqueParametre(cle: string) {
  return (await api.get<{ historique: ChangementParametre[] }>(`${FINANCE}/parametres/${cle}/`)).data;
}

export async function modifierParametre(cle: string, valeur: string, motif: string) {
  return (await api.patch<ParametreFinance>(`${FINANCE}/parametres/${cle}/`, { valeur, motif })).data;
}

// --- Internal transfers, money accounts and bank statements (GL-22)

export type StatutVirement = "en_attente" | "ecrit" | "refuse" | "annule";

export interface CompteArgentFinance {
  code: string;
  libelle: string;
  type: string;
  compte_syscohada: string | null;
  actif: boolean;
  actif_depuis: string | null;
  solde: number;
  nb_lignes: number;
  banque: boolean;
  /** Account of passage or guarantee fund: no statement, no transfer */
  sans_releve: boolean;
}

export interface VirementFinance {
  id: string;
  numero: string;
  date_virement: string;
  source: string;
  source_libelle: string;
  destination: string;
  destination_libelle: string;
  montant: number;
  motif: string;
  reference_externe: string;
  statut: StatutVirement;
  demandee_par: string;
  motif_annulation: string;
}

export interface ReleveImporte {
  id: string;
  compte_argent_id: string;
  debut: string;
  fin: string;
  nb_lignes: number;
  nom_fichier: string;
  importe_le: string;
}

export interface ListeVirements extends PageFinance<VirementFinance> {
  comptes: CompteArgentFinance[];
  releves: ReleveImporte[];
  seuil: number;
  peut_saisir: boolean;
  peut_activer: boolean;
}

export interface NouveauVirement {
  date_virement: string;
  source: string;
  destination: string;
  montant: number;
  motif: string;
  reference_externe: string;
  fichiers: File[];
}

export interface ColonnesReleve {
  date: string;
  libelle: string;
  debit: string;
  credit: string;
  montant: string;
  reference: string;
}

export interface ResultatReleve {
  debut: string;
  fin: string;
  lignes: number;
  rapprochees: number;
  inconnues: number;
  jours: { jour: string; etat: string; ecart: number | null; message: string }[];
}

export async function lireVirements(page: number, statut = "") {
  return (await api.get<ListeVirements>(`${FINANCE}/virements/${parametres({ statut, page })}`)).data;
}

export async function saisirVirement(v: NouveauVirement) {
  const corps = new FormData();
  for (const cle of ["date_virement", "source", "destination", "motif", "reference_externe"] as const) corps.append(cle, v[cle]);
  corps.append("montant", String(v.montant));
  for (const f of v.fichiers) corps.append("fichiers", f);
  return (await api.post<VirementFinance & { attente_validation: boolean }>(`${FINANCE}/virements/`, corps)).data;
}

export async function annulerVirement(id: string, motif: string) {
  return (await api.post<VirementFinance>(`${FINANCE}/virements/${id}/annuler/`, { motif })).data;
}

export async function activerCompteArgent(code: string, actif: boolean) {
  return (await api.post<CompteArgentFinance>(`${FINANCE}/comptes-argent/${code}/activation/`, { actif })).data;
}

export async function importerReleve(compte: string, fichier: File, colonnes: ColonnesReleve) {
  const corps = new FormData();
  corps.append("compte", compte);
  corps.append("fichier", fichier);
  for (const [cle, valeur] of Object.entries(colonnes)) corps.append(`col_${cle}`, valeur);
  return (await api.post<ResultatReleve>(`${FINANCE}/releves-bancaires/`, corps)).data;
}
