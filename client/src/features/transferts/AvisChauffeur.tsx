"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface NoteChauffeur {
  note: number;
  ponctualite: number;
  conduite: number;
  amabilite: number;
  commentaire: string;
}

const CRITERES = ["note", "ponctualite", "conduite", "amabilite"] as const;

/**
 * The traveller rates their driver after a ride (a transfer, or a rental with a driver): seen by the Kwa-Ba team only,
 * it feeds the drivers' quarterly level review.
 */
export default function AvisChauffeur({ envoyer, onEnvoye }: {
  envoyer: (avis: NoteChauffeur) => Promise<unknown>; onEnvoye: () => void;
}) {
  const t = useTranslations("avisChauffeur");
  const [avis, setAvis] = useState<NoteChauffeur>({ note: 0, ponctualite: 0, conduite: 0, amabilite: 0, commentaire: "" });
  const [envoi, setEnvoi] = useState(false);
  const complet = CRITERES.every((c) => avis[c] > 0);

  const valider = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnvoi(true);
    try {
      await envoyer(avis);
      toast.success(t("merci"));
      onEnvoye();
    } catch (err) {
      toast.error(apiErrorMessage(err, t("erreur")));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <form onSubmit={valider} className="bg-background rounded-3xl border border-gray-100 p-5 sm:p-6 space-y-4" aria-label={t("titre")}>
      <div>
        <h2 className="font-heading font-bold text-dark text-lg">{t("titre")}</h2>
        <p className="text-sm text-gray-600 mt-1">{t("aide")}</p>
      </div>
      {CRITERES.map((critere) => (
        <fieldset key={critere} className="flex flex-wrap items-center justify-between gap-2">
          <legend className="text-sm font-semibold text-dark float-left">{t(`criteres.${critere}`)}</legend>
          <div className="flex gap-1" role="radiogroup" aria-label={t(`criteres.${critere}`)}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" role="radio" aria-checked={avis[critere] === n} aria-label={t("etoiles", { n })}
                onClick={() => setAvis({ ...avis, [critere]: n })} className="relative zone-tactile p-1">
                <Star size={22} className={cn(n <= avis[critere] ? "fill-amber-400 text-amber-400" : "text-gray-300")} aria-hidden />
              </button>
            ))}
          </div>
        </fieldset>
      ))}
      <label className="block text-sm"><span className="block font-semibold text-dark mb-1">{t("commentaire")}</span>
        <textarea rows={3} maxLength={2000} value={avis.commentaire} onChange={(e) => setAvis({ ...avis, commentaire: e.target.value })}
          className="w-full px-3 py-2 border border-gray-200 rounded-xl text-base sm:text-sm" /></label>
      <button type="submit" disabled={!complet || envoi} className="px-5 py-2.5 rounded-full bg-primary text-white text-sm font-bold disabled:opacity-50">
        {envoi ? t("envoi") : t("envoyer")}
      </button>
    </form>
  );
}
