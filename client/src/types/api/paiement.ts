export interface OperateurPaiement {
  code: string;
  nom: string;
}

export interface PaysPaiement {
  code: "TG" | "BJ" | "BF" | "NE" | "ML";
  nom: string;
  indicatif: string;
  chiffres: number;
  operateurs: OperateurPaiement[];
}

export type MoyenPaiement = "mobile_money" | "carte" | "paypal";

export interface DevisSejour {
  prix_nuits: number;
  frais_service: number;
  /** Cleaning fee of the listing type, once per stay (0 for a hotel room) */
  frais_menage: number;
  /** Escrowed deposit (ADR-036), given back after the stay */
  deposit: number;
  /** Enhanced guarantee fee, and the damages it covers */
  guarantee_fee: number;
  guarantee_cover: number;
  total: number;
}

export interface ConfigPaiement {
  actif: boolean;
  /** Offered methods: mobile_money and carte go through FedaPay, paypal is charged in euros. */
  moyens: MoyenPaiement[];
  fcfa_par_euro: number;
  environnement: "sandbox" | "live";
  frais_voyageur: number;
  /** Reduced fees: loyal customer, Stay Pack + Driver. */
  frais_reduits: number;
  commission_hote: number;
  /** Commission by partner type (price grid). */
  commissions: { particulier: number; hotel: number; fondateur: number };
  /** Cleaning fee by listing type (FCFA), paid back to the host in full */
  frais_menage: Record<string, number>;
  delai_paiement_minutes: number;
  pays: PaysPaiement[];
  /** Deposit of the short stays chosen by the host (ADR-036), read in the finance referential. */
  deposit: DepositRules;
}

export interface DepositRules {
  /** Escrowed deposit: rate of the nights' price, at most, proposed, and above which the host is warned (%). */
  rate_max: number;
  rate_proposed: number;
  rate_warning: number;
  /** Below `minimum` (FCFA) no deposit; above `ceiling`, capped; rounded to `rounding`. */
  minimum: number;
  ceiling: number;
  rounding: number;
  /** The enhanced guarantee covers damages up to this multiple of its fee. */
  guarantee_multiple: number;
  /** Option c open to the hosts (off until FedaPay confirms an escrow without fees). */
  escrow_open: boolean;
}

export type StatutPaiement = "en_attente" | "reussi" | "echoue" | "annule";

export interface StatutPaiementReservation {
  reservation: "pending" | "confirmed" | "cancelled";
  paiement: StatutPaiement | null;
  expire_le: string | null;
  annule_par: string;
}

export interface ProfilVersement {
  pays: PaysPaiement["code"];
  operateur: string;
  numero: string;
  titulaire: string;
  mis_a_jour_le?: string;
}

export type StatutVersement = "planifie" | "en_cours" | "envoye" | "echoue";

export interface Versement {
  id: string;
  reservation_id: string;
  reference: string;
  hebergement: string;
  voyageur: string;
  check_in: string;
  check_out: string;
  montant_brut: number;
  commission: number;
  montant: number;
  statut: StatutVersement;
  date_prevue: string;
  envoye_le: string | null;
  probleme: string;
}

export interface Revenus {
  totaux: { a_venir: number; en_cours: number; verse: number; commission: number };
  profil_complet: boolean;
  /** This host's commission today, in % (8, 12 for a hotel, 5 during the Founders Programme). */
  commission_pourcent: number;
  /** Partner type set by the team: individual (8 %), hotel (12 %), founder (5 % for 6 months). */
  partenaire: "particulier" | "hotel" | "fondateur";
  frais_voyageur_pourcent: number;
  versements: Versement[];
}
