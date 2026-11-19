"use client";

import { useLocale, useTranslations } from "next-intl";
import { AC } from "@/components/legal/LegalPage";
import { useReglagesSite } from "@/lib/site";
import { formats } from "@/lib/utils";

/**
 * Registered office of KWA-BA, read from the company sheet of the back-office (the address of invoices and
 * contracts): changing it there is enough, without touching the code. "To be completed" while it is empty.
 */
export function AdresseSociete() {
  const t = useTranslations("legal");
  const adresse = useReglagesSite().data?.societe?.adresse;
  if (!adresse) return <AC>{t("adresseSiege")}</AC>;
  return <>{adresse}</>;
}

/** Share capital of KWA-BA, from the finance parameter `capital_social` (Finance → Paramètres). */
export function CapitalSociete() {
  const t = useTranslations("legal");
  const locale = useLocale();
  const capital = useReglagesSite().data?.societe?.capital;
  if (!capital) return <AC>{t("capitalSocial")}</AC>;
  return <>{formats(locale).formatFcfa(capital)}</>;
}
