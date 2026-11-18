// Labels of the ledger codes shown in the back-office (the codes themselves are data of the finance module)

export const TIERS: Record<string, string> = {
  hote: "Hôte", hotel: "Hôtel", voyageur: "Voyageur", chauffeur: "Chauffeur", proprietaire: "Propriétaire",
  prestataire: "Prestataire", apporteur: "Apporteur",
};

export const OFFRES: Record<string, string> = {
  COURTE_DUREE: "Courte durée", HOTEL: "Hôtel", TRANSFERT: "Transfert", VOITURE_CH: "Voiture avec chauffeur",
  VOITURE_SANS: "Voiture sans chauffeur", STRUCTURE: "Structure", EVASION: "Évasion",
};

/** Colour of a nature's badge, by family (R revenue, D expense, T third-party funds, C deposit). */
export const FAMILLES: Record<string, string> = {
  R: "bg-emerald-50 text-emerald-800", D: "bg-orange-50 text-orange-800", T: "bg-sky-50 text-sky-800",
  C: "bg-violet-50 text-violet-800",
};
