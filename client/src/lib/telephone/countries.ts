/**
 * Countries offered by the phone field (PhoneInput): West Africa, and France at the top for the diaspora.
 * Same list as src/shared/telephone/countries.ts of the app (kwa-ba-mobile): change both at once.
 */

export type CodePays =
  | "FR"
  | "BJ"
  | "BF"
  | "CV"
  | "CI"
  | "GM"
  | "GH"
  | "GN"
  | "GW"
  | "LR"
  | "ML"
  | "MR"
  | "NE"
  | "NG"
  | "SN"
  | "SL"
  | "TG";

export interface PaysTelephone {
  /** ISO 3166-1 alpha-2 code, also the key of the flag. */
  iso: CodePays;
  nom: string;
  nomEn: string;
  /** Dialling code, without the +. ITU codes never start one another, so the first match is the right one. */
  indicatif: string;
  /** Allowed lengths of the national number (digits after the dialling code, trunk 0 removed). */
  longueurs: readonly number[];
  /**
   * The leading 0 belongs to the number and is never removed: Benin (01…) and Côte d'Ivoire (01, 05, 07…) since
   * their move to 10 digits.
   */
  zeroSignificatif?: boolean;
  /** National number shown as placeholder. */
  exemple: string;
}

export const PAYS_TELEPHONE: readonly PaysTelephone[] = [
  // Diaspora: remove this line to take France out of the list
  { iso: "FR", nom: "France", nomEn: "France", indicatif: "33", longueurs: [9], exemple: "6 12 34 56 78" },
  { iso: "BJ", nom: "Bénin", nomEn: "Benin", indicatif: "229", longueurs: [10], zeroSignificatif: true, exemple: "01 90 12 34 56" },
  { iso: "BF", nom: "Burkina Faso", nomEn: "Burkina Faso", indicatif: "226", longueurs: [8], exemple: "70 12 34 56" },
  { iso: "CV", nom: "Cap-Vert", nomEn: "Cape Verde", indicatif: "238", longueurs: [7], exemple: "991 12 34" },
  { iso: "CI", nom: "Côte d'Ivoire", nomEn: "Côte d'Ivoire", indicatif: "225", longueurs: [10], zeroSignificatif: true, exemple: "07 12 34 56 78" },
  { iso: "GM", nom: "Gambie", nomEn: "Gambia", indicatif: "220", longueurs: [7], exemple: "301 23 45" },
  { iso: "GH", nom: "Ghana", nomEn: "Ghana", indicatif: "233", longueurs: [9], exemple: "24 123 4567" },
  { iso: "GN", nom: "Guinée", nomEn: "Guinea", indicatif: "224", longueurs: [9], exemple: "601 12 34 56" },
  { iso: "GW", nom: "Guinée-Bissau", nomEn: "Guinea-Bissau", indicatif: "245", longueurs: [9], exemple: "955 012 345" },
  { iso: "LR", nom: "Liberia", nomEn: "Liberia", indicatif: "231", longueurs: [7, 8, 9], exemple: "77 012 3456" },
  { iso: "ML", nom: "Mali", nomEn: "Mali", indicatif: "223", longueurs: [8], exemple: "70 12 34 56" },
  { iso: "MR", nom: "Mauritanie", nomEn: "Mauritania", indicatif: "222", longueurs: [8], exemple: "22 12 34 56" },
  { iso: "NE", nom: "Niger", nomEn: "Niger", indicatif: "227", longueurs: [8], exemple: "90 12 34 56" },
  { iso: "NG", nom: "Nigeria", nomEn: "Nigeria", indicatif: "234", longueurs: [8, 9, 10], exemple: "802 123 4567" },
  { iso: "SN", nom: "Sénégal", nomEn: "Senegal", indicatif: "221", longueurs: [9], exemple: "77 123 45 67" },
  { iso: "SL", nom: "Sierra Leone", nomEn: "Sierra Leone", indicatif: "232", longueurs: [8], exemple: "76 123 456" },
  { iso: "TG", nom: "Togo", nomEn: "Togo", indicatif: "228", longueurs: [8], exemple: "90 12 34 56" },
];

/** Country selected when the field starts empty, unless the screen passes another one. */
export const PAYS_PAR_DEFAUT: CodePays = "TG";
