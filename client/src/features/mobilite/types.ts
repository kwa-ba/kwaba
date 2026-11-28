/** A vehicle range of the shared mobility referential (T-H1): the same word for a transfer and a rental. */
export interface Gamme {
  code: string;
  /** Name and description in the language of the request. */
  nom: string;
  description: string;
  /** Capacity promised for a transfer in this range. */
  places: number;
  bagages: number;
  propose_transfert: boolean;
  propose_location: boolean;
  ordre: number;
  actif: boolean;
}

/** A range as edited in the back-office (both languages). */
export interface GammeAdmin {
  code: string;
  libelle: string;
  libelle_en: string;
  description: string;
  description_en: string;
  places: number;
  bagages: number;
  propose_transfert: boolean;
  propose_location: boolean;
  ordre: number;
  actif: boolean;
}

/** A vehicle record as the driver form chooses it (module locations, read from the back-office list). */
export interface VehiculeFiche {
  id: number;
  nom: string;
  gamme: string;
  immatriculation: string;
  places: number;
  bagages: number;
  actif: boolean;
  proprietaire_id: number | null;
  proprietaire_nom: string;
  proprietaire_compte_id: string | null;
}

/** The Kwa-Ba account a partner record is linked to (decision 3: the roles add up). */
export interface CompteLie {
  id: string;
  email: string;
  nom: string;
}
