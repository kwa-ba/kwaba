"use client";

import NextLink from "next/link";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

/**
 * Page shown for an address that does not exist, in the language of the site (never Next.js' default English page).
 * `espace`: back-office (French only, link to its home) or the public site (link to the home page of the language).
 */
export default function PageIntrouvable({ espace = "site" }: { espace?: "site" | "backoffice" }) {
  const t = useTranslations("introuvable");
  const bouton = "bg-primary text-white font-bold px-6 py-3 rounded-xl";
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-muted text-sm font-semibold">404</p>
      <h1 className="text-dark font-heading font-bold text-xl">{t("titre")}</h1>
      <p className="text-muted max-w-md">{t("texte")}</p>
      {espace === "backoffice" ? (
        <NextLink href="/backoffice" className={bouton}>{t("retourBackoffice")}</NextLink>
      ) : (
        <Link href="/" className={bouton}>{t("retourAccueil")}</Link>
      )}
    </div>
  );
}
