import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cloturerMois, creerRapport, deciderValidation, lireValidations, lireAuxiliaires, lireBalance, lireComptes, lireControlesCloture, lireGrandLivre,
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
