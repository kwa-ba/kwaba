import { afterEach, describe, expect, it, vi } from "vitest";
import { verifyTwoFactor } from "./two-factor";

function apiAnswer(status: number, body: unknown) {
  const call = vi.fn(async (..._args: Parameters<typeof fetch>) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", call);
  return call;
}

describe("verifyTwoFactor", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the code with the session's tokens and returns the marked pair", async () => {
    const call = apiAnswer(200, { access: "marked-access", refresh: "marked-refresh" });
    await expect(verifyTwoFactor("access", "refresh", "482913")).resolves.toEqual({ access: "marked-access", refresh: "marked-refresh" });
    const [url, init] = call.mock.calls[0];
    expect(String(url)).toMatch(/\/v1\/auth\/two-factor\/verify\/$/);
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer access");
    expect(JSON.parse(String(init?.body))).toEqual({ code: "482913", refresh: "refresh" });
  });

  it("returns the refusal of the API", async () => {
    apiAnswer(400, { code: "invalid_code", detail: "Code incorrect ou déjà utilisé." });
    await expect(verifyTwoFactor("a", "r", "000000")).resolves.toEqual({
      error: { code: "invalid_code", detail: "Code incorrect ou déjà utilisé.", retryAfter: undefined },
    });
  });

  it("keeps the delay of a blocked account", async () => {
    apiAnswer(429, { code: "too_many_attempts", detail: "Trop de tentatives. Réessayez dans 15 min.", retry_after: 840 });
    const result = await verifyTwoFactor("a", "r", "000000");
    expect("error" in result && result.error.retryAfter).toBe(840);
  });

  it("says when the server cannot be reached, and never returns tokens it did not get", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    await expect(verifyTwoFactor("a", "r", "1")).resolves.toEqual({ error: { code: "unreachable", detail: "Impossible de contacter le serveur." } });
    apiAnswer(200, { detail: "ok" });
    await expect(verifyTwoFactor("a", "r", "1")).resolves.toMatchObject({ error: { code: "error" } });
  });
});
