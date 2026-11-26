"use client";

import { useRouter } from "@/i18n/navigation";
import { signIn } from "next-auth/react";
import { useTranslations } from "next-intl";
import { useConfigPublique } from "@/providers/PublicConfigProvider";
import { adresseRetourApple, estAnnulationApple } from "./apple";

interface ReponseApple {
  authorization?: { id_token?: string; code?: string };
  user?: { name?: { firstName?: string; lastName?: string } };
}

declare global {
  interface Window {
    AppleID?: {
      auth: {
        init: (config: { clientId: string; scope: string; redirectURI: string; usePopup: boolean }) => void;
        signIn: () => Promise<ReponseApple>;
      };
    };
  }
}

const SCRIPT_APPLE = "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js";

let chargement: Promise<void> | null = null;
function chargerScriptApple(): Promise<void> {
  if (window.AppleID) return Promise.resolve();
  if (!chargement) {
    chargement = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = SCRIPT_APPLE;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => { chargement = null; reject(new Error("script Apple indisponible")); };
      document.head.appendChild(s);
    });
  }
  return chargement;
}

interface AppleButtonProps {
  label: string;
  callbackUrl: string;
  onError: (message: string) => void;
}

/**
 * « Continuer avec Apple » (ADR-045): Apple's window, then the same route as the iOS app (auth/apple/) through
 * next-auth. Apple's look (black, white logo). Hidden while APPLE_SERVICES_ID is not configured (client.env).
 */
export default function AppleButton({ label, callbackUrl, onError }: AppleButtonProps) {
  const router = useRouter();
  const t = useTranslations("auth");
  const { appleServicesId } = useConfigPublique();

  if (!appleServicesId) return null;

  const handleClick = async () => {
    onError("");
    // Apple's script is only loaded on click: no request to Apple for visitors who do not use it
    try {
      await chargerScriptApple();
    } catch {
      onError(t("appleIndisponible"));
      return;
    }
    if (!window.AppleID) {
      onError(t("appleIndisponible"));
      return;
    }
    const redirectUri = adresseRetourApple(window.location.origin);
    window.AppleID.auth.init({ clientId: appleServicesId, scope: "name email", redirectURI: redirectUri, usePopup: true });

    let reponse: ReponseApple;
    try {
      reponse = await window.AppleID.auth.signIn();
    } catch (erreur) {
      if (!estAnnulationApple(erreur)) onError(t("appleRefus"));
      return;
    }
    const idToken = reponse.authorization?.id_token;
    if (!idToken) {
      onError(t("appleRefus"));
      return;
    }
    try {
      const res = await signIn("apple-id-token", {
        redirect: false,
        idToken,
        code: reponse.authorization?.code ?? "",
        redirectUri,
        // Given by Apple only the very first time
        firstName: reponse.user?.name?.firstName ?? "",
        lastName: reponse.user?.name?.lastName ?? "",
      });
      if (res?.error) {
        const messages: Record<string, string> = {
          inactive: t("desactive"),
          too_many_attempts: t("tropDeTentatives"),
          serveur: t("serveurInjoignable"),
        };
        onError(messages[res.code ?? ""] ?? t("appleRefus"));
        return;
      }
      router.push(callbackUrl);
      router.refresh();
    } catch {
      onError(t("serveurInjoignable"));
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="w-full flex items-center justify-center gap-3 bg-black text-white rounded-2xl py-3.5 text-sm font-medium hover:bg-neutral-800 transition-colors shadow-xs"
    >
      <svg width="16" height="18" viewBox="0 0 17 20" aria-hidden fill="currentColor">
        <path d="M14.04 10.63c-.02-2.05 1.68-3.04 1.75-3.09-.96-1.4-2.44-1.59-2.96-1.61-1.26-.13-2.46.74-3.1.74-.64 0-1.62-.72-2.67-.7-1.37.02-2.64.8-3.35 2.03-1.43 2.48-.37 6.15 1.03 8.16.68.98 1.49 2.09 2.55 2.05 1.02-.04 1.41-.66 2.65-.66 1.24 0 1.58.66 2.67.64 1.1-.02 1.8-1 2.47-1.99.78-1.14 1.1-2.25 1.12-2.3-.02-.01-2.14-.82-2.16-3.27zM12.02 4.6c.56-.68.94-1.63.84-2.57-.81.03-1.79.54-2.37 1.22-.52.6-.98 1.57-.86 2.49.9.07 1.83-.46 2.39-1.14z" />
      </svg>
      {label}
    </button>
  );
}
