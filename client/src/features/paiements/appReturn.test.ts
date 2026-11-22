import { describe, expect, it } from "vitest";
import { appLink } from "./appReturn";

const ID = "4f1c2a9e-0b7d-4c3e-9a51-2d6f8e0c1b3a";

describe("appLink", () => {
  it("opens the payment screen of the app, query kept", () => {
    expect(appLink("kwaba", ["reservation", "paiement", ID], "annule=1")).toBe(`kwaba://reservation/paiement/${ID}?annule=1`);
    expect(appLink("kwaba-preprod", ["transfert", ID], "")).toBe(`kwaba-preprod://transfert/${ID}`);
    expect(appLink("kwaba", ["location", ID], "")).toBe(`kwaba://location/${ID}`);
  });

  it("refuses another scheme or another path", () => {
    expect(appLink("https", ["transfert", ID], "")).toBeNull();
    expect(appLink("javascript", ["transfert", ID], "")).toBeNull();
    expect(appLink("kwaba", ["profil"], "")).toBeNull();
    expect(appLink("kwaba", ["transfert", "pas-un-id"], "")).toBeNull();
    expect(appLink("kwaba", ["transfert", ID, "..", "profil"], "")).toBeNull();
  });
});
