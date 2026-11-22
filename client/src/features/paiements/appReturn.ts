/**
 * Return from a payment started in the mobile app (ADR-041): the provider sends the traveller to
 * /retour-app/<scheme>/<path>, which opens <scheme>://<path> in the app. Only the app's schemes and the paths of its
 * payment screens are accepted: never an open redirect.
 */
export const APP_SCHEMES = ["kwaba", "kwaba-preprod"] as const;

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const PAYMENT_SCREENS = new RegExp(`^(reservation/paiement|transfert|location)/${UUID}$`, "i");

/** The app's address, or null when the scheme or the path is not one of the app's. */
export function appLink(scheme: string, path: string[], query: string): string | null {
  const screen = path.join("/");
  if (!(APP_SCHEMES as readonly string[]).includes(scheme) || !PAYMENT_SCREENS.test(screen)) return null;
  return `${scheme}://${screen}${query ? `?${query}` : ""}`;
}
