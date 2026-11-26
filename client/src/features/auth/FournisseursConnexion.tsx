"use client";

import { useTranslations } from "next-intl";
import { useConfigPublique } from "@/providers/PublicConfigProvider";
import AppleButton from "./AppleButton";
import GoogleButton from "./GoogleButton";

interface FournisseursConnexionProps {
  /** Sign-in or sign-up: only the labels change, the API creates the account at the first sign-in. */
  mode: "connexion" | "inscription";
  callbackUrl: string;
  onError: (message: string) => void;
}

/**
 * Sign-in through Apple and Google, above the email form: Apple first (its guidelines ask it to be at least as
 * visible as the others), each one hidden while not configured, and « ou par e-mail » only when one of them shows.
 */
export default function FournisseursConnexion({ mode, callbackUrl, onError }: FournisseursConnexionProps) {
  const t = useTranslations("auth");
  const { appleServicesId, googleClientId } = useConfigPublique();
  if (!appleServicesId && !googleClientId) return null;

  return (
    <>
      <div className="space-y-3">
        <AppleButton
          label={mode === "connexion" ? t("continuerApple") : t("inscriptionApple")}
          callbackUrl={callbackUrl}
          onError={onError}
        />
        <GoogleButton
          label={mode === "connexion" ? t("continuerGoogle") : t("inscriptionGoogle")}
          callbackUrl={callbackUrl}
          onError={onError}
        />
      </div>
      <div className="flex items-center gap-4 my-6">
        <div className="flex-1 h-px bg-gray-200" />
        <span className="text-gray-400 text-xs font-medium">{t("ouParEmail")}</span>
        <div className="flex-1 h-px bg-gray-200" />
      </div>
    </>
  );
}
