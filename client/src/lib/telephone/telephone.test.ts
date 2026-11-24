import { describe, expect, it } from "vitest";
import { PAYS_TELEPHONE } from "./countries";
import { DRAPEAUX } from "./drapeaux";
import { filtrerPays, lireTelephone, nettoyerSaisie, normaliserTelephone, verifierTelephone, versE164 } from "./telephone";

/** Same cases as src/shared/telephone/telephone.test.ts of the app. */
describe("phone field", () => {
  it("list: France first, one SVG flag per country, unique dialling codes", () => {
    expect(PAYS_TELEPHONE[0]!.iso).toBe("FR");
    expect(PAYS_TELEPHONE).toHaveLength(17);
    for (const p of PAYS_TELEPHONE) expect(DRAPEAUX[p.iso]).toMatch(/^<svg /);
    expect(new Set(PAYS_TELEPHONE.map((p) => p.indicatif)).size).toBe(17);
  });

  it("E.164: spaces, dashes and the leading 0 ignored", () => {
    expect(versE164({ pays: "TG", texte: "90 12-34.56" })).toBe("+22890123456");
    expect(versE164({ pays: "FR", texte: "06 12 34 56 78" })).toBe("+33612345678");
    expect(versE164({ pays: "GH", texte: "024 123 4567" })).toBe("+233241234567");
    expect(versE164({ pays: "TG", texte: "" })).toBe("");
    expect(versE164({ pays: "TG", texte: "0" })).toBe("");
  });

  it("Benin and Côte d'Ivoire: the leading 0 belongs to the number", () => {
    expect(versE164({ pays: "BJ", texte: "01 90 12 34 56" })).toBe("+2290190123456");
    expect(versE164({ pays: "CI", texte: "07 12 34 56 78" })).toBe("+2250712345678");
    expect(verifierTelephone("+2290190123456")).toBeNull();
    expect(verifierTelephone("+22990123456")).toMatchObject({ code: "longueur" });
  });

  it("pasted with a dialling code: the country follows", () => {
    expect(lireTelephone("+221 77 123 45 67", "TG")).toEqual({ pays: "SN", texte: "77 123 45 67" });
    expect(lireTelephone("00228 90 12 34 56", "FR")).toEqual({ pays: "TG", texte: "90 12 34 56" });
    expect(lireTelephone("+22890123456", "TG")).toEqual({ pays: "TG", texte: "90123456" });
    expect(lireTelephone("90 12 34 56", "ML")).toEqual({ pays: "ML", texte: "90 12 34 56" });
  });

  it("another dialling code: the whole number is kept", () => {
    expect(lireTelephone("+1 555 123 4567", "TG")).toEqual({ pays: null, texte: "+1 555 123 4567" });
    expect(versE164({ pays: null, texte: "+1 555 123 4567" })).toBe("+15551234567");
    expect(lireTelephone("+", "TG")).toEqual({ pays: null, texte: "+" });
    expect(verifierTelephone("+15551234567")).toBeNull();
    expect(verifierTelephone("+1555")).toEqual({ code: "international" });
  });

  it("numbers already saved: older formats read again", () => {
    expect(normaliserTelephone("+228 90 00 00 00")).toBe("+22890000000");
    expect(normaliserTelephone("90000000")).toBe("+22890000000");
    expect(normaliserTelephone("")).toBe("");
    expect(lireTelephone("+33 6 12 34 56 78")).toEqual({ pays: "FR", texte: "6 12 34 56 78" });
  });

  it("typed text cleaned: letters removed, + only at the start", () => {
    expect(nettoyerSaisie("tel: 90 12 34 56")).toBe("90 12 34 56");
    expect(nettoyerSaisie("+228+90")).toBe("+22890");
    expect(nettoyerSaisie("0033 6")).toBe("+33 6");
  });

  it("length checked per country", () => {
    expect(verifierTelephone("+22890123456")).toBeNull();
    expect(verifierTelephone("+2289012345")).toMatchObject({ code: "longueur", pays: { iso: "TG" } });
    expect(verifierTelephone("+231770123456")).toBeNull();
    expect(verifierTelephone("+2317701234")).toBeNull();
    expect(verifierTelephone("")).toBeNull();
  });

  it("search by name, code or dialling code", () => {
    expect(filtrerPays("senegal").map((p) => p.iso)).toEqual(["SN"]);
    expect(filtrerPays("+228").map((p) => p.iso)).toEqual(["TG"]);
    expect(filtrerPays("22").length).toBeGreaterThan(5);
    expect(filtrerPays("Gambia", "en").map((p) => p.iso)).toEqual(["GM"]);
    expect(filtrerPays("ci").map((p) => p.iso)).toContain("CI");
    expect(filtrerPays("")).toHaveLength(17);
  });
});
