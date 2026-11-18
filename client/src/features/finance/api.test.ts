import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "@/lib/api";
import * as finance from "./api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const F = "/v1/admin/finance";

describe("finance (back-office)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("n'envoie pas les filtres vides et joint les listes par des virgules", () => {
    expect(finance.parametres({ a: "", b: undefined, c: null, d: "x", e: 2, f: [], g: ["R", "D"] })).toBe("?d=x&e=2&g=R%2CD");
    expect(finance.parametres({ a: "" })).toBe("");
  });

  it("lit le grand livre filtré et paginé", async () => {
    await finance.lireMouvements({ famille: "R", piece: "RES-1", sens: "" }, 2);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/mouvements/?famille=R&piece=RES-1&page=2&page_size=20`);
    await finance.lireReferentiels();
    expect(api.get).toHaveBeenLastCalledWith(`${F}/referentiels/`);
  });

  it("lit les livres sur une période", async () => {
    await finance.lireLivreJournal("2026-11-01", "2026-11-30", "VT", 1);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/livre-journal/?debut=2026-11-01&fin=2026-11-30&journal=VT&page=1&page_size=50`);
    await finance.lireGrandLivreCompte("47121", "HOTE-1", "2026-11-01", "2026-11-30", 3);
    expect(api.get).toHaveBeenLastCalledWith(
      `${F}/grand-livre-compte/?compte=47121&auxiliaire=HOTE-1&debut=2026-11-01&fin=2026-11-30&page=3&page_size=50`);
    await finance.lireAuxiliaires("47121");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/comptes/47121/auxiliaires/`);
    await finance.lireBalance("2026-11-01", "2026-11-30");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/balance/?debut=2026-11-01&fin=2026-11-30`);
    await finance.lirePilotage("2026-11");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/pilotage/?mois=2026-11`);
    expect(finance.urlExportEcritures("2026-11-01", "2026-11-30")).toBe(`${F}/export/ecritures/?debut=2026-11-01&fin=2026-11-30`);
  });

  it("clôture un mois avec la confirmation saisie", async () => {
    await finance.lireControlesCloture("2026-10");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/cloture/2026-10/`);
    await finance.cloturerMois("2026-10", "10/2026");
    expect(api.post).toHaveBeenLastCalledWith(`${F}/cloture/2026-10/`, { confirmation: "10/2026" });
  });

  it("lance un rapport enregistré ou libre, et en enregistre un nouveau", async () => {
    await finance.lireResultatRapport({ code: "recettes_type" }, "2026-11-01", "2026-11-30");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/rapports/resultat/?code=recettes_type&debut=2026-11-01&fin=2026-11-30`);
    await finance.lireResultatRapport({ axe1: "moyen", axe2: "mois", familles: ["D"] }, "2026-11-01", "2026-11-30");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/rapports/resultat/?axe1=moyen&axe2=mois&familles=D&debut=2026-11-01&fin=2026-11-30`);
    const nouveau = { code: "frais_moyen", titre: "Frais par moyen", axe1: "moyen", axe2: null, familles: ["D"] };
    await finance.creerRapport(nouveau);
    expect(api.post).toHaveBeenLastCalledWith(`${F}/rapports/`, nouveau);
  });
});

describe("double validation (GL-10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit les demandes et envoie une décision, avec le motif d'un refus seulement", async () => {
    await finance.lireValidations("en_attente");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/validations/?statut=en_attente`);
    await finance.lireValidations("");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/validations/`);
    await finance.deciderValidation("v1", "approuver", "ignoré");
    expect(api.post).toHaveBeenLastCalledWith(`${F}/validations/v1/approuver/`, {});
    await finance.deciderValidation("v1", "refuser", "Séjour maintenu");
    expect(api.post).toHaveBeenLastCalledWith(`${F}/validations/v1/refuser/`, { motif: "Séjour maintenu" });
  });
});
