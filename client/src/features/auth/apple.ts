/**
 * Return address declared for the Services ID in Apple's portal (the home page of each site). Apple answers in its
 * window (usePopup), and asks for the same address again when the API exchanges the code (web_redirect_uri).
 */
export function adresseRetourApple(origine: string): string {
  return `${origine.replace(/\/+$/, "")}/`;
}

/** The person closed Apple's window or refused: nothing to say. */
export function estAnnulationApple(erreur: unknown): boolean {
  const code = (erreur as { error?: unknown } | null)?.error;
  return code === "popup_closed_by_user" || code === "user_cancelled_authorize";
}
