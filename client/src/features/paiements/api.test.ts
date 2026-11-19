import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "@/lib/api";
import * as paiements from "./api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

describe("paiements", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const m of [api.get, api.post, api.put]) vi.mocked(m).mockResolvedValue({ data: { url: "https://pay" } });
  });

  it("lit la configuration et le devis calculé par l'API", async () => {
    await paiements.lireConfig();
    expect(api.get).toHaveBeenLastCalledWith("/v1/paiements/config/");
    await paiements.lireDevis("h1", { nuits: 3, nb_unites: 1 });
    expect(api.get).toHaveBeenLastCalledWith("/v1/hebergements/h1/devis/", { params: { nuits: 3, nb_unites: 1 } });
  });

  it("démarre le paiement d'une réservation, avec ou sans moyen choisi", async () => {
    await expect(paiements.demarrerPaiementReservation("r1", "carte" as never)).resolves.toBe("https://pay");
    expect(api.post).toHaveBeenLastCalledWith("/v1/paiements/reservations/r1/payer/", { moyen: "carte" });
    await paiements.demarrerPaiementReservation("r1");
    expect(api.post).toHaveBeenLastCalledWith("/v1/paiements/reservations/r1/payer/", {});
  });

  it("démarre le paiement d'un transfert et d'une location", async () => {
    await paiements.demarrerPaiementTransfert("t1", "carte" as never);
    expect(api.post).toHaveBeenLastCalledWith("/v1/transferts/t1/payer/", { moyen: "carte" });
    await paiements.demarrerPaiementLocation("l1", "carte" as never);
    expect(api.post).toHaveBeenLastCalledWith("/v1/locations/l1/payer/", { moyen: "carte" });
  });

  it("lit le statut d'un paiement", async () => {
    await paiements.lireStatutReservation("r1");
    expect(api.get).toHaveBeenLastCalledWith("/v1/paiements/reservations/r1/statut/");
  });

  it("enregistre le compte de remboursement à l'adresse donnée", async () => {
    const compte = { pays: "TG", operateur: "moov", numero: "90000000" };
    await paiements.enregistrerCompteRemboursement(paiements.adresseCompteReservation("r1"), compte);
    expect(api.put).toHaveBeenCalledWith("/v1/paiements/reservations/r1/compte-remboursement/", compte);
  });

  it("lit les revenus et le profil de versement", async () => {
    await paiements.lireRevenus();
    expect(api.get).toHaveBeenLastCalledWith("/v1/paiements/revenus/");
    await paiements.lireProfilVersement();
    expect(api.get).toHaveBeenLastCalledWith("/v1/paiements/profil-versement/");
    const profil = { pays: "TG" as const, operateur: "moov", numero: "90", titulaire: "K" };
    await paiements.enregistrerProfilVersement(profil);
    expect(api.put).toHaveBeenLastCalledWith("/v1/paiements/profil-versement/", profil);
  });
});

describe("remboursements au back-office (GL-9)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lit la liste et l'aperçu d'un séjour, puis rembourse ou demande une validation", async () => {
    const p = paiements;
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await p.lireRemboursements("a_traiter", 2);
    expect(api.get).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/remboursements/", { params: { statut: "a_traiter", page: 2 } });
    await p.lireApercuRemboursement("RES-AF2026-3A43");
    expect(api.get).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/remboursements/apercu/", { params: { reference: "RES-AF2026-3A43" } });

    vi.mocked(api.post).mockResolvedValueOnce({ status: 202, data: { detail: "Deuxième personne", validation: "v1" } });
    await expect(p.rembourserSejour("r1", "plateforme", "Hôte injoignable")).resolves.toEqual({ attenteValidation: true, message: "Deuxième personne" });
    expect(api.post).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/remboursements/sejour/",
      { reservation_id: "r1", bareme: "plateforme", motif: "Hôte injoignable" });

    vi.mocked(api.post).mockResolvedValueOnce({ data: { id: "x" } });
    await p.agirSurRemboursement("x", "manuel", { reference: "FP-1" });
    expect(api.post).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/remboursements/x/manuel/", { reference: "FP-1" });
  });
});

describe("versements aux partenaires (GL-11)", () => {
  it("lit les versements filtrés, relance un versement et demande un remboursement", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    await paiements.lireVersementsPartenaires("echoue");
    expect(api.get).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/versements/", { params: { statut: "echoue" } });
    await paiements.lireVersementsPartenaires("");
    expect(api.get).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/versements/", { params: {} });
    await paiements.relancerVersement("hote", "v1");
    expect(api.post).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/versements/hote/v1/relancer/", {});
    await paiements.relancerRecuperation("r1");
    expect(api.post).toHaveBeenLastCalledWith("/v1/admin/paiements/finances/recuperations/r1/relancer/", {});
  });
});
