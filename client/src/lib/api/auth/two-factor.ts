import { getApiBaseUrl } from "@/lib/api-url";

/** Refusal of a second factor code, shown on the code screen. */
export type TwoFactorError = { code: string; detail: string; retryAfter?: number };

export type TwoFactorResult = { access: string; refresh: string } | { error: TwoFactorError };

const UNREACHABLE: TwoFactorError = { code: "unreachable", detail: "Impossible de contacter le serveur." };

/**
 * Sends the back-office second factor code with the session's tokens (ADR-028). Called by the Next server only (jwt
 * callback of src/auth.ts): the marked pair it gets back goes into the encrypted cookie, never to the browser.
 */
export async function verifyTwoFactor(accessToken: string, refreshToken: string, code: string): Promise<TwoFactorResult> {
  let res: Response;
  try {
    res = await fetch(`${getApiBaseUrl()}/v1/auth/two-factor/verify/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ code, refresh: refreshToken }),
      cache: "no-store",
    });
  } catch {
    return { error: UNREACHABLE };
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (res.ok && typeof data.access === "string" && typeof data.refresh === "string") {
    return { access: data.access, refresh: data.refresh };
  }
  return {
    error: {
      code: typeof data.code === "string" ? data.code : "error",
      detail: typeof data.detail === "string" ? data.detail : "Code refusé. Réessayez.",
      retryAfter: typeof data.retry_after === "number" ? data.retry_after : undefined,
    },
  };
}
