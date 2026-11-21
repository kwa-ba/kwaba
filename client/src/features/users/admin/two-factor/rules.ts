import type { TwoFactorStatus } from "@/types/api/admin";

export type GateScreen = "loading" | "open" | "setup" | "code";

/** Which screen the back-office guard shows. The API stays the only judge: an unreadable status opens the page,
 * whose requests are refused if the second factor is missing. */
export function gateScreen({ isAdmin, loading, status, now }: {
  isAdmin: boolean; loading: boolean; status: TwoFactorStatus | undefined; now: number;
}): GateScreen {
  if (!isAdmin) return "open";
  if (loading) return "loading";
  if (!status) return "open";
  if (!status.enabled) return "setup";
  return isVerified(status, now) ? "open" : "code";
}

export function isVerified(status: TwoFactorStatus, now: number): boolean {
  return !!status.expires_at && Date.parse(status.expires_at) > now;
}

/** Milliseconds before the code is asked again, null if it is not verified. */
export function msBeforeExpiry(status: TwoFactorStatus | undefined, now: number): number | null {
  if (!status?.expires_at) return null;
  const ms = Date.parse(status.expires_at) - now;
  return ms > 0 ? ms : null;
}

/** Setup key by groups of 4, easier to type by hand: "JBSW Y3DP EHPK 3PXP". */
export function groupKey(secret: string): string {
  return (secret.match(/.{1,4}/g) ?? []).join(" ");
}

/** Only digits, at most 6: what the code field keeps of what is typed or pasted. */
export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "").slice(0, 6);
}

/** Backup code being typed, in capitals, letters, digits and dash only. */
export function backupCodeInput(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 9);
}

/** Text file of the backup codes, to download or copy. */
export function backupCodesText(codes: string[], account: string, date: Date): string {
  return [
    "Kwa-Ba · codes de secours du back-office",
    `Compte : ${account}`,
    `Générés le ${date.toLocaleDateString("fr-FR")}`,
    "Chaque code ne fonctionne qu'une seule fois.",
    "",
    ...codes.map((code, i) => `${String(i + 1).padStart(2, "0")}  ${code}`),
    "",
  ].join("\n");
}
