import { describe, expect, it, vi } from "vitest";

vi.mock("next-auth/react", () => ({ getSession: vi.fn(), signOut: vi.fn() }));

/** What the adapter receives: the request as it leaves, after the interceptors and the transforms. */
type Envoi = { data?: unknown; headers: Record<string, unknown> };

import api from "./api";

describe("client de l'API", () => {
  it("envoie un formulaire avec fichiers en multipart, sans le convertir en JSON", async () => {
    let envoye: Envoi | undefined;
    const adapter = async (config: Envoi) => {
      envoye = config;
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
    const corps = new FormData();
    corps.append("image", new File(["png"], "komi.png", { type: "image/png" }));

    await api.post("/v1/admin/transferts/chauffeurs/1/photo/", corps, { adapter } as never);

    expect(envoye?.data).toBeInstanceOf(FormData);
    expect((envoye?.data as FormData).get("image")).toBeInstanceOf(File);
    expect(String(envoye?.headers["Content-Type"])).toContain("multipart/form-data");
  });

  it("garde le JSON pour un corps ordinaire", async () => {
    let envoye: Envoi | undefined;
    const adapter = async (config: Envoi) => {
      envoye = config;
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };

    await api.post("/v1/x/", { motif: "Saisie en double" }, { adapter } as never);

    expect(envoye?.data).toBe('{"motif":"Saisie en double"}');
    expect(String(envoye?.headers["Content-Type"])).toContain("application/json");
  });
});
