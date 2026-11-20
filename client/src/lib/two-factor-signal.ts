/**
 * The API refused a back-office request because the second factor is missing or expired (403 two_factor_required,
 * ADR-028). lib/ knows no module: the two-factor guard of features/users listens to this signal.
 */
type Listener = () => void;

const listeners = new Set<Listener>();

export function onTwoFactorRequired(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function signalTwoFactorRequired(): void {
  for (const listener of listeners) listener();
}

/** Code of the API answer that asks for the second factor. */
export const TWO_FACTOR_REQUIRED = "two_factor_required";
