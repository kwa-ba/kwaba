import { type CodePays, PAYS_PAR_DEFAUT, PAYS_TELEPHONE, type PaysTelephone } from "./countries";

/**
 * Rules of the phone field, without React: what is typed or pasted becomes a country and a national number, then
 * the E.164 sent to the API (+22890123456). Same file as src/shared/telephone/telephone.ts of the app (kwa-ba-mobile).
 */

/** What the field holds: the selected country (null: another dialling code, typed after a +) and the typed text. */
export interface SaisieTelephone {
  pays: CodePays | null;
  texte: string;
}

export type ErreurTelephone =
  /** National number of the wrong length for its country. */
  | { code: "longueur"; pays: PaysTelephone }
  /** Number with another dialling code: 8 to 15 digits in all, as the API checks. */
  | { code: "international" };

const chiffres = (texte: string) => texte.replace(/\D/g, "");

/** Code of the API (payment settings) that the phone field knows. */
export function estCodePays(code: string | null | undefined): code is CodePays {
  return PAYS_TELEPHONE.some((p) => p.iso === code);
}

export function paysTelephone(iso: CodePays | null | undefined): PaysTelephone | undefined {
  return iso ? PAYS_TELEPHONE.find((p) => p.iso === iso) : undefined;
}

/** Country of an international number by its dialling code (codes never start one another). */
function paysDeLIndicatif(numero: string): PaysTelephone | undefined {
  const d = chiffres(numero);
  return PAYS_TELEPHONE.find((p) => d.startsWith(p.indicatif));
}

/**
 * Typed or pasted text: digits, spaces, dots, dashes and brackets only, a + at the start only, and « 00 » before
 * a dialling code read as « + ».
 */
export function nettoyerSaisie(texte: string): string {
  let propre = texte.replace(/[^\d\s.\-()+]/g, "").trimStart();
  if (propre.startsWith("00")) propre = `+${propre.slice(2)}`;
  const international = propre.startsWith("+");
  propre = propre.replace(/\+/g, "");
  return international ? `+${propre}` : propre;
}

/** Text after the first `nombre` digits, separators kept (« +228 90 12 » → « 90 12 »). */
function apresIndicatif(texte: string, nombre: number): string {
  let vus = 0;
  let i = 0;
  while (i < texte.length && vus < nombre) {
    if (/\d/.test(texte[i]!)) vus += 1;
    i += 1;
  }
  return texte.slice(i).replace(/^[\s.\-()]+/, "");
}

/**
 * Reads a value (E.164 saved by the API, an older format with spaces, or what was just typed or pasted). With a +,
 * the dialling code picks the country; a code outside the list keeps the whole number (pays null). Without +, the
 * number belongs to `pays`.
 */
export function lireTelephone(valeur: string, pays: CodePays | null = PAYS_PAR_DEFAUT): SaisieTelephone {
  const texte = nettoyerSaisie(valeur);
  if (!texte.startsWith("+")) return { pays, texte };
  const trouve = paysDeLIndicatif(texte);
  if (trouve) return { pays: trouve.iso, texte: apresIndicatif(texte, trouve.indicatif.length) };
  return { pays: null, texte };
}

/** Digits of the national number, without the trunk 0 of a national format (unless it belongs to the number). */
function numeroNational(pays: PaysTelephone, texte: string): string {
  const d = chiffres(texte);
  return !pays.zeroSignificatif && d.startsWith("0") ? d.slice(1) : d;
}

/** E.164 sent to the API (+22890123456); "" when no number is typed. */
export function versE164({ pays, texte }: SaisieTelephone): string {
  const infos = paysTelephone(pays);
  if (!infos) {
    const d = chiffres(texte);
    return d ? `+${d}` : "";
  }
  const national = numeroNational(infos, texte);
  return national ? `+${infos.indicatif}${national}` : "";
}

/** Any value (E.164, older format, number without code) as E.164; a number without code is read in `pays`. */
export function normaliserTelephone(valeur: string, pays: CodePays = PAYS_PAR_DEFAUT): string {
  return versE164(lireTelephone(valeur, pays));
}

/** E.164 of a Mobile Money account saved as country and number without the code (`pays`, `numero` of the API). */
export function composerTelephone(pays: CodePays | string | null | undefined, numero: string | null | undefined): string {
  const infos = PAYS_TELEPHONE.find((p) => p.iso === pays);
  const d = chiffres(numero ?? "");
  return infos && d ? `+${infos.indicatif}${d}` : "";
}

/** Country and number without the code of a value, as the Mobile Money routes of the API expect them. */
export function decomposerTelephone(valeur: string, pays: CodePays = PAYS_PAR_DEFAUT): { pays: CodePays | null; numero: string } {
  const e164 = normaliserTelephone(valeur, pays);
  const infos = paysDeLIndicatif(e164);
  return infos ? { pays: infos.iso, numero: e164.slice(1 + infos.indicatif.length) } : { pays: null, numero: chiffres(e164) };
}

/**
 * Number for reading or printing (« +228 90 12 34 56 »): grouped like the country's example when the length
 * matches, otherwise the E.164 as it is.
 */
export function formaterTelephone(valeur: string, pays: CodePays = PAYS_PAR_DEFAUT): string {
  const e164 = normaliserTelephone(valeur, pays);
  const infos = paysDeLIndicatif(e164);
  if (!infos) return e164;
  const national = e164.slice(1 + infos.indicatif.length);
  const groupes = infos.exemple.split(" ").map((g) => g.length);
  if (groupes.reduce((a, b) => a + b, 0) !== national.length) return `+${infos.indicatif} ${national}`;
  let i = 0;
  const morceaux = groupes.map((n) => national.slice(i, (i += n)));
  return `+${infos.indicatif} ${morceaux.join(" ")}`;
}

/** Checks a value (E.164 or older format); null when it is empty or valid. */
export function verifierTelephone(valeur: string, pays: CodePays = PAYS_PAR_DEFAUT): ErreurTelephone | null {
  const e164 = normaliserTelephone(valeur, pays);
  if (!e164) return null;
  const infos = paysDeLIndicatif(e164);
  if (infos) {
    const longueur = e164.length - 1 - infos.indicatif.length;
    return infos.longueurs.includes(longueur) ? null : { code: "longueur", pays: infos };
  }
  const longueur = e164.length - 1;
  return longueur >= 8 && longueur <= 15 ? null : { code: "international" };
}

/** Lengths of a country for a message: « 8 », « 7 à 9 » (« 7 to 9 » with `a` = "to"). */
export function longueursAttendues(pays: PaysTelephone, a: string): string {
  const min = Math.min(...pays.longueurs);
  const max = Math.max(...pays.longueurs);
  return min === max ? String(min) : `${min} ${a} ${max}`;
}

/** Search of the country list: name (accents ignored), ISO code or dialling code (with or without +). */
export function filtrerPays(recherche: string, langue: "fr" | "en" = "fr"): PaysTelephone[] {
  const sansAccent = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const q = sansAccent(recherche.trim());
  if (!q) return [...PAYS_TELEPHONE];
  const code = q.replace(/^\+|^00/, "");
  return PAYS_TELEPHONE.filter(
    (p) =>
      sansAccent(langue === "en" ? p.nomEn : p.nom).includes(q) ||
      sansAccent(p.nom).includes(q) ||
      p.iso.toLowerCase() === q ||
      (/^\d+$/.test(code) && p.indicatif.startsWith(code)),
  );
}
