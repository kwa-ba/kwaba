import { describe, expect, it } from "vitest";
import { adresseRetourApple, estAnnulationApple } from "./apple";

describe("connexion avec Apple sur le site (ADR-045)", () => {
  it("adresse de retour : la page d'accueil du site, comme web_redirect_uri de l'API", () => {
    expect(adresseRetourApple("https://kwa-ba.com")).toBe("https://kwa-ba.com/");
    expect(adresseRetourApple("https://preprod.kwa-ba.com/")).toBe("https://preprod.kwa-ba.com/");
  });

  it("fenêtre fermée ou refus : pas d'erreur affichée", () => {
    expect(estAnnulationApple({ error: "popup_closed_by_user" })).toBe(true);
    expect(estAnnulationApple({ error: "user_cancelled_authorize" })).toBe(true);
    expect(estAnnulationApple({ error: "invalid_client" })).toBe(false);
    expect(estAnnulationApple(null)).toBe(false);
  });
});
