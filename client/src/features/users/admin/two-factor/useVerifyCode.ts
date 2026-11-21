import { useState } from "react";
import { useSession } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";
import { TWO_FACTOR_KEY } from "../../hooks";

/**
 * Sends a code (app or backup code) through the session: the Next server checks it with the API and keeps the marked
 * tokens in the encrypted cookie (src/auth.ts). Resolves to true once the session is verified.
 */
export function useVerifyCode() {
  const { update } = useSession();
  const queryClient = useQueryClient();
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const verifier = async (code: string): Promise<boolean> => {
    setEnvoi(true);
    setErreur(null);
    try {
      const session = await update({ twoFactorCode: code });
      if (!session) {
        setErreur("Session expirée : reconnectez-vous.");
        return false;
      }
      if (session.twoFactorError) {
        setErreur(session.twoFactorError.detail);
        return false;
      }
      await queryClient.invalidateQueries({ queryKey: TWO_FACTOR_KEY });
      return true;
    } catch {
      setErreur("Impossible de contacter le serveur.");
      return false;
    } finally {
      setEnvoi(false);
    }
  };

  return { verifier, envoi, erreur };
}
