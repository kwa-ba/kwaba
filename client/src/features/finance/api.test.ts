import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "@/lib/api";
import * as finance from "./api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));

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

describe("registre des cautions (GL-13, GL-14)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: {} });
  });

  it("lit le registre, les retards et les pièces d'une caution", async () => {
    await finance.lireCautions("detenue", false);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/cautions/?statut=detenue`);
    await finance.lireCautions("", true);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/cautions/?retard=1`);
    await finance.lireJustificatifs("location", "l1");
    expect(api.get).toHaveBeenLastCalledWith("/v1/admin/documents/justificatifs/?objet_type=location&objet_id=l1");
    expect(finance.urlDocumentCaution("RET-2026-00001")).toBe("/v1/admin/documents/cautions/RET-2026-00001/pdf/");
  });
});

describe("rapprochement FedaPay (GL-12)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit le mois et une journée, et importe une période", async () => {
    await finance.lireRapprochements("2026-11-01");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/rapprochement/?mois=2026-11&compte=FEDAPAY`);
    await finance.lireRapprochementJour("2026-11-18");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/rapprochement/2026-11-18/?compte=FEDAPAY`);
    await finance.importerRapprochement("2026-11-01", "2026-11-18");
    expect(api.post).toHaveBeenLastCalledWith("/v1/admin/paiements/rapprochement/importer/", { debut: "2026-11-01", fin: "2026-11-18" });
  });

  it("envoie une régularisation avec ses pièces en multipart", async () => {
    const piece = new File(["%PDF"], "releve.pdf", { type: "application/pdf" });
    await finance.regulariserRapprochement("2026-11-18", { reference: "999", nature: "D01", offre: "COURTE_DUREE", sens: "sortie",
      montant: 250, motif: "Frais FedaPay non annoncés", fichiers: [piece] });
    const [url, corps] = vi.mocked(api.post).mock.calls.at(-1)!;
    expect(url).toBe(`${F}/rapprochement/2026-11-18/regulariser/?compte=FEDAPAY`);
    const form = corps as FormData;
    expect([form.get("reference"), form.get("nature"), form.get("sens"), form.get("montant")]).toEqual(["999", "D01", "sortie", "250"]);
    expect((form.getAll("fichiers")[0] as File).name).toBe("releve.pdf");
  });
});

describe("dépenses (GL-15)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post, api.patch]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit les dépenses filtrées et en saisit une avec son justificatif", async () => {
    await finance.lireDepenses({ nature: "D10", statut: "" }, 2);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/depenses/?nature=D10&page=2&page_size=20`);
    const piece = new File(["%PDF"], "facture.pdf", { type: "application/pdf" });
    await finance.saisirDepense({ date_depense: "2026-11-18", nature: "D10", offre: "STRUCTURE", montant: 30000,
      libelle: "Hébergement", fournisseur: "f1", associe: "a1", reference_facture: "FR-1", fichiers: [piece] });
    const [url, corps] = vi.mocked(api.post).mock.calls.at(-1)!;
    expect(url).toBe(`${F}/depenses/`);
    const form = corps as FormData;
    expect([form.get("nature"), form.get("montant"), form.get("fournisseur"), form.get("associe")]).toEqual(["D10", "30000", "f1", "a1"]);
    expect((form.getAll("fichiers")[0] as File).name).toBe("facture.pdf");
    await finance.annulerDepense("d1", "Saisie en double");
    expect(api.post).toHaveBeenLastCalledWith(`${F}/depenses/d1/annuler/`, { motif: "Saisie en double" });
  });

  it("crée ou modifie un fournisseur et un associé", async () => {
    await finance.enregistrerFournisseur({ nom: "OVH", nif: "123" });
    expect(api.post).toHaveBeenLastCalledWith(`${F}/fournisseurs/`, { nom: "OVH", nif: "123" });
    await finance.enregistrerFournisseur({ id: "f1", nom: "OVH", actif: false });
    expect(api.patch).toHaveBeenLastCalledWith(`${F}/fournisseurs/f1/`, { nom: "OVH", actif: false });
    await finance.enregistrerAssocie({ nom: "Ama" });
    expect(api.post).toHaveBeenLastCalledWith(`${F}/associes/`, { nom: "Ama" });
  });
});

describe("comptes des associés et fonds de garantie (GL-16, GL-17)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post, api.patch]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit les comptes courants et le relevé d'un associé, et change sa part du capital", async () => {
    await finance.lireComptesCourants();
    expect(api.get).toHaveBeenLastCalledWith(`${F}/associes/comptes/`);
    await finance.lireReleveAssocie("a1");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/associes/a1/releve/`);
    await finance.enregistrerAssocie({ id: "a1", nom: "Ama", capital_souscrit: 200000 });
    expect(api.patch).toHaveBeenLastCalledWith(`${F}/associes/a1/`, { nom: "Ama", capital_souscrit: 200000 });
  });

  it("lit le fonds, écrit les dotations, couvre un sinistre et l'annule", async () => {
    await finance.lireFondsGarantie();
    expect(api.get).toHaveBeenLastCalledWith(`${F}/fonds-garantie/`);
    await finance.doterFondsGarantie();
    expect(api.post).toHaveBeenLastCalledWith(`${F}/fonds-garantie/doter/`, {});
    await finance.doterFondsGarantie("2026-10-01");
    expect(api.post).toHaveBeenLastCalledWith(`${F}/fonds-garantie/doter/`, { mois: "2026-10" });
    const sinistre = { depense: "d1", montant: 15000, decision_reference: "DEC-1", motif: "Vitre cassée chez un hôte" };
    await finance.imputerSinistre(sinistre);
    expect(api.post).toHaveBeenLastCalledWith(`${F}/fonds-garantie/sinistres/`, sinistre);
    await finance.annulerSinistre("s1", "Mauvaise dépense");
    expect(api.post).toHaveBeenLastCalledWith(`${F}/fonds-garantie/sinistres/s1/annuler/`, { motif: "Mauvaise dépense" });
  });
});

describe("paramètres (GL-20)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post, api.patch]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit le référentiel et l'historique d'un paramètre, et le modifie avec son motif", async () => {
    await finance.lireParametres();
    expect(api.get).toHaveBeenLastCalledWith(`${F}/parametres/`);
    await finance.lireHistoriqueParametre("fonds_garantie_cible");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/parametres/fonds_garantie_cible/`);
    await finance.modifierParametre("fonds_garantie_cible", "500000", "Décision des associés");
    expect(api.patch).toHaveBeenLastCalledWith(`${F}/parametres/fonds_garantie_cible/`, { valeur: "500000", motif: "Décision des associés" });
  });
});

describe("virements et relevés bancaires (GL-22)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post, api.patch]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit les virements, en saisit un avec sa preuve, ouvre un compte et importe un relevé", async () => {
    await finance.lireVirements(2);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/virements/?page=2`);
    const preuve = new File(["%PDF"], "avis.pdf", { type: "application/pdf" });
    await finance.saisirVirement({ date_virement: "2026-12-03", source: "FEDAPAY", destination: "BANQUE_EXP", montant: 200000,
      motif: "Retrait du mois", reference_externe: "FP-1", fichiers: [preuve] });
    const [url, corps] = vi.mocked(api.post).mock.calls.at(-1)!;
    expect(url).toBe(`${F}/virements/`);
    expect([(corps as FormData).get("source"), (corps as FormData).get("montant")]).toEqual(["FEDAPAY", "200000"]);
    await finance.activerCompteArgent("BANQUE_EXP", true);
    expect(api.post).toHaveBeenLastCalledWith(`${F}/comptes-argent/BANQUE_EXP/activation/`, { actif: true });
    const csv = new File(["Date;Libellé;Débit;Crédit"], "releve.csv", { type: "text/csv" });
    await finance.importerReleve("BANQUE_EXP", csv, { date: "Date", libelle: "Libellé", debit: "Débit", credit: "Crédit", montant: "", reference: "" });
    const [urlReleve, corpsReleve] = vi.mocked(api.post).mock.calls.at(-1)!;
    expect(urlReleve).toBe(`${F}/releves-bancaires/`);
    expect([(corpsReleve as FormData).get("compte"), (corpsReleve as FormData).get("col_debit")]).toEqual(["BANQUE_EXP", "Débit"]);
  });
});

describe("pilotage, relevés, rapport aux associés et inventaire (GL-18, GL-21, GL-23)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post, api.patch]) vi.mocked(m).mockResolvedValue({ data: {} });
  });

  it("lit le tableau de bord, un relevé, le rapport et le livre d'inventaire, avec leurs exports", async () => {
    await finance.lireTableauDeBord("2026-11-01");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/tableau-de-bord/?mois=2026-11`);
    expect(finance.urlExportTableau("2026-11-01")).toBe(`${F}/tableau-de-bord/?mois=2026-11&export=csv`);
    await finance.lireReleveCompte("hote", "h1", "2026-11-01");
    expect(api.get).toHaveBeenLastCalledWith(`${F}/releves-partenaires/?tiers_type=hote&tiers_id=h1&mois=2026-11`);
    expect(finance.urlReleveCompte("hote", "h1", "2026-11-01")).toContain("export=pdf");
    await finance.commenterRapportAssocies("2026-10-01", "Bon mois");
    expect(api.patch).toHaveBeenLastCalledWith(`${F}/rapport-associes/`, { mois: "2026-10", commentaire: "Bon mois" });
    await finance.lireLivreInventaire(2026);
    expect(api.get).toHaveBeenLastCalledWith(`${F}/inventaire/?annee=2026`);
    await finance.ecrireInventaire(2026);
    expect(api.post).toHaveBeenLastCalledWith(`${F}/inventaire/`, { annee: 2026 });
  });
});
