import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activerCompteArgent, annulerVirement, importerReleve, lireVirements, saisirVirement, type ColonnesReleve,
  type NouveauVirement,
  lireHistoriqueParametre, lireParametres, modifierParametre,
  annulerSinistre, doterFondsGarantie, imputerSinistre, lireComptesCourants, lireFondsGarantie, lireReleveAssocie,
  type NouveauSinistre,
  annulerDepense, cloturerMois, creerRapport, deciderValidation, enregistrerAssocie, enregistrerFournisseur,
  importerRapprochement, lireAssocies, lireDepenses, lireFournisseurs, saisirDepense, type AssocieFinance,
  type FiltresDepenses, type FournisseurFinance, type NouvelleDepense, lireCautions, lireRapprochementJour, lireRapprochements,
  regulariserRapprochement, type NouvelleRegularisation, lireJustificatifs, lireValidations, lireAuxiliaires, lireBalance, lireComptes, lireControlesCloture, lireGrandLivre,
  lireGrandLivreCompte, lireLivreJournal, lireMoisComptables, lireMouvements, lirePilotage, lireRapports,
  lireReferentiels, lireResultatRapport, type DemandeRapport, type FiltresMouvements, type NouveauRapport,
} from "./api";

// One cache key per read of the module (documentation/frontieres-front.md)
export const CLES_FINANCE = {
  tout: ["admin", "finance"] as const,
  grandLivre: ["admin", "finance", "grand-livre"] as const,
  referentiels: ["admin", "finance", "referentiels"] as const,
  mouvements: (filtres: FiltresMouvements, page: number) => ["admin", "finance", "mouvements", filtres, page] as const,
  livreJournal: (debut: string, fin: string, journal: string, page: number) =>
    ["admin", "finance", "livre-journal", debut, fin, journal, page] as const,
  comptes: ["admin", "finance", "comptes"] as const,
  auxiliaires: (compte: string) => ["admin", "finance", "comptes", compte, "auxiliaires"] as const,
  grandLivreCompte: (compte: string, auxiliaire: string, debut: string, fin: string, page: number) =>
    ["admin", "finance", "grand-livre-compte", compte, auxiliaire, debut, fin, page] as const,
  balance: (debut: string, fin: string) => ["admin", "finance", "balance", debut, fin] as const,
  pilotage: (mois: string) => ["admin", "finance", "pilotage", mois] as const,
  cloture: ["admin", "finance", "cloture"] as const,
  controles: (mois: string) => ["admin", "finance", "cloture", mois] as const,
  rapports: ["admin", "finance", "rapports"] as const,
  resultat: (demande: DemandeRapport, debut: string, fin: string) => ["admin", "finance", "rapports", demande, debut, fin] as const,
  validations: (statut: string) => ["admin", "finance", "validations", statut] as const,
  cautions: (statut: string, retard: boolean) => ["admin", "finance", "cautions", statut, retard] as const,
  justificatifs: (objetType: string, objetId: string) => ["admin", "finance", "justificatifs", objetType, objetId] as const,
  rapprochement: ["admin", "finance", "rapprochement"] as const,
  rapprochements: (mois: string, compte = "FEDAPAY") => ["admin", "finance", "rapprochement", "mois", mois, compte] as const,
  rapprochementJour: (jour: string, compte = "FEDAPAY") => ["admin", "finance", "rapprochement", "jour", jour, compte] as const,
  depenses: (filtres: FiltresDepenses, page: number) => ["admin", "finance", "depenses", filtres, page] as const,
  fournisseurs: ["admin", "finance", "fournisseurs"] as const,
  associes: ["admin", "finance", "associes"] as const,
  comptesCourants: ["admin", "finance", "associes", "comptes"] as const,
  releveAssocie: (id: string) => ["admin", "finance", "associes", "releve", id] as const,
  fondsGarantie: ["admin", "finance", "fonds-garantie"] as const,
  parametres: ["admin", "finance", "parametres"] as const,
  virements: (page: number, statut: string) => ["admin", "finance", "virements", page, statut] as const,
  historiqueParametre: (cle: string) => ["admin", "finance", "parametres", cle] as const,
};

/** The ledger at a glance (invariants, balances, sums owed, latest lines), read only. */
export function useGrandLivre() {
  return useQuery({ queryKey: CLES_FINANCE.grandLivre, queryFn: lireGrandLivre });
}

/** Codes offered by the filters: they rarely change. */
export function useReferentielsFinance() {
  return useQuery({ queryKey: CLES_FINANCE.referentiels, queryFn: lireReferentiels, staleTime: 10 * 60_000 });
}

export function useMouvements(filtres: FiltresMouvements, page: number) {
  return useQuery({ queryKey: CLES_FINANCE.mouvements(filtres, page), queryFn: () => lireMouvements(filtres, page), placeholderData: keepPreviousData });
}

export function useLivreJournal(debut: string, fin: string, journal: string, page: number) {
  return useQuery({
    queryKey: CLES_FINANCE.livreJournal(debut, fin, journal, page), queryFn: () => lireLivreJournal(debut, fin, journal, page),
    enabled: !!debut && !!fin && debut <= fin, placeholderData: keepPreviousData,
  });
}

export function useComptes() {
  return useQuery({ queryKey: CLES_FINANCE.comptes, queryFn: lireComptes });
}

export function useAuxiliaires(compte: string) {
  return useQuery({ queryKey: CLES_FINANCE.auxiliaires(compte), queryFn: () => lireAuxiliaires(compte), enabled: !!compte });
}

export function useGrandLivreCompte(compte: string, auxiliaire: string, debut: string, fin: string, page: number) {
  return useQuery({
    queryKey: CLES_FINANCE.grandLivreCompte(compte, auxiliaire, debut, fin, page),
    queryFn: () => lireGrandLivreCompte(compte, auxiliaire, debut, fin, page),
    enabled: !!compte && !!debut && !!fin && debut <= fin, placeholderData: keepPreviousData,
  });
}

export function useBalance(debut: string, fin: string) {
  return useQuery({ queryKey: CLES_FINANCE.balance(debut, fin), queryFn: () => lireBalance(debut, fin), enabled: !!debut && !!fin && debut <= fin });
}

/** `mois`: « 2026-11 » */
export function usePilotage(mois: string) {
  return useQuery({ queryKey: CLES_FINANCE.pilotage(mois), queryFn: () => lirePilotage(mois) });
}

export function useMoisComptables() {
  return useQuery({ queryKey: CLES_FINANCE.cloture, queryFn: lireMoisComptables });
}

export function useControlesCloture(mois: string | null) {
  return useQuery({ queryKey: CLES_FINANCE.controles(mois ?? ""), queryFn: () => lireControlesCloture(mois!), enabled: !!mois });
}

/** Locks a month; every figure of the module is read again afterwards. */
export function useCloturerMois() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ mois, confirmation }: { mois: string; confirmation: string }) => cloturerMois(mois, confirmation),
    onSuccess: () => client.invalidateQueries({ queryKey: CLES_FINANCE.tout }),
  });
}

export function useRapports() {
  return useQuery({ queryKey: CLES_FINANCE.rapports, queryFn: lireRapports });
}

export function useResultatRapport(demande: DemandeRapport | null, debut: string, fin: string) {
  return useQuery({
    queryKey: CLES_FINANCE.resultat(demande ?? {}, debut, fin), queryFn: () => lireResultatRapport(demande!, debut, fin),
    enabled: !!demande && !!debut && !!fin && debut <= fin,
  });
}

export function useCreerRapport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (rapport: NouveauRapport) => creerRapport(rapport),
    onSuccess: () => client.invalidateQueries({ queryKey: CLES_FINANCE.rapports }),
  });
}

export function useValidations(statut: string) {
  return useQuery({ queryKey: CLES_FINANCE.validations(statut), queryFn: () => lireValidations(statut) });
}

/** Approves or refuses: the operation may have changed bookings, refunds and payouts, read again everywhere. */
export function useDeciderValidation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, motif }: { id: string; decision: "approuver" | "refuser"; motif?: string }) =>
      deciderValidation(id, decision, motif),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin"] }),
  });
}

export function useCautions(statut: string, retard: boolean) {
  return useQuery({ queryKey: CLES_FINANCE.cautions(statut, retard), queryFn: () => lireCautions(statut, retard) });
}

export function useJustificatifs(objetType: string, objetId: string | null) {
  return useQuery({ queryKey: CLES_FINANCE.justificatifs(objetType, objetId ?? ""), queryFn: () => lireJustificatifs(objetType, objetId!), enabled: !!objetId });
}

/** Every finished day of the month reconciled with FedaPay (GL-12): green, red or never imported. */
export function useRapprochements(mois: string, compte = "FEDAPAY") {
  return useQuery({ queryKey: CLES_FINANCE.rapprochements(mois, compte), queryFn: () => lireRapprochements(mois, compte),
    placeholderData: keepPreviousData });
}

export function useRapprochementJour(jour: string | null, compte = "FEDAPAY") {
  return useQuery({ queryKey: CLES_FINANCE.rapprochementJour(jour ?? "", compte), queryFn: () => lireRapprochementJour(jour!, compte),
    enabled: !!jour });
}

/** An import writes real fees in the ledger: every finance read may change. */
export function useImporterRapprochement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ debut, fin }: { debut: string; fin: string }) => importerRapprochement(debut, fin),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }),
  });
}

export function useRegulariser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jour, regularisation, compte }: { jour: string; regularisation: NouvelleRegularisation; compte?: string }) =>
      regulariserRapprochement(jour, regularisation, compte),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }),
  });
}

/** The expenses of Kwa-Ba with their filters (GL-15). */
export function useDepenses(filtres: FiltresDepenses, page: number) {
  return useQuery({ queryKey: CLES_FINANCE.depenses(filtres, page), queryFn: () => lireDepenses(filtres, page),
    placeholderData: keepPreviousData });
}

/** An expense written or cancelled changes the ledger: every finance read may change. */
export function useSaisirDepense() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (d: NouvelleDepense) => saisirDepense(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useAnnulerDepense() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ id, motif }: { id: string; motif: string }) => annulerDepense(id, motif),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useFournisseurs() {
  return useQuery({ queryKey: CLES_FINANCE.fournisseurs, queryFn: lireFournisseurs });
}

export function useAssocies() {
  return useQuery({ queryKey: CLES_FINANCE.associes, queryFn: lireAssocies });
}

export function useEnregistrerFournisseur() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (f: Partial<FournisseurFinance> & { nom: string }) => enregistrerFournisseur(f),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.fournisseurs }) });
}

export function useEnregistrerAssocie() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (a: Partial<AssocieFinance> & { nom: string }) => enregistrerAssocie(a),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.associes }) });
}

/** What Kwa-Ba owes each associate, with the share capital (GL-16). */
export function useComptesCourants() {
  return useQuery({ queryKey: CLES_FINANCE.comptesCourants, queryFn: lireComptesCourants });
}

export function useReleveAssocie(id: string | null) {
  return useQuery({ queryKey: CLES_FINANCE.releveAssocie(id ?? ""), queryFn: () => lireReleveAssocie(id as string),
    enabled: !!id });
}

/** The guarantee fund, its allocations and the losses it covers (GL-17). */
export function useFondsGarantie() {
  return useQuery({ queryKey: CLES_FINANCE.fondsGarantie, queryFn: lireFondsGarantie });
}

/** Allocations and covers write in the ledger: every finance read may change. */
export function useDoterFondsGarantie() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (mois?: string) => doterFondsGarantie(mois),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useImputerSinistre() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (s: NouveauSinistre) => imputerSinistre(s),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useAnnulerSinistre() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ id, motif }: { id: string; motif: string }) => annulerSinistre(id, motif),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

/** The referential of the steered parameters and their history (GL-20). */
export function useParametres() {
  return useQuery({ queryKey: CLES_FINANCE.parametres, queryFn: lireParametres });
}

export function useHistoriqueParametre(cle: string | null) {
  return useQuery({ queryKey: CLES_FINANCE.historiqueParametre(cle ?? ""), queryFn: () => lireHistoriqueParametre(cle as string),
    enabled: !!cle });
}

/** A value changed may move any finance figure (thresholds, rates): every finance read is refreshed. */
export function useModifierParametre() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ cle, valeur, motif }: { cle: string; valeur: string; motif: string }) =>
    modifierParametre(cle, valeur, motif), onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

/** Internal transfers, money accounts and statements (GL-22). */
export function useVirements(page: number, statut = "") {
  return useQuery({ queryKey: CLES_FINANCE.virements(page, statut), queryFn: () => lireVirements(page, statut),
    placeholderData: keepPreviousData });
}

/** A transfer, an account opened or a statement imported moves the ledger or the reconciliation. */
export function useSaisirVirement() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (v: NouveauVirement) => saisirVirement(v),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useAnnulerVirement() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ id, motif }: { id: string; motif: string }) => annulerVirement(id, motif),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useActiverCompteArgent() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ code, actif }: { code: string; actif: boolean }) => activerCompteArgent(code, actif),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}

export function useImporterReleve() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ compte, fichier, colonnes }: { compte: string; fichier: File; colonnes: ColonnesReleve }) =>
    importerReleve(compte, fichier, colonnes), onSuccess: () => qc.invalidateQueries({ queryKey: CLES_FINANCE.tout }) });
}
