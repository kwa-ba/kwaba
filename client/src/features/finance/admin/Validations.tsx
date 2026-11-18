"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Check, ShieldCheck, X } from "lucide-react";
import { Pill } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import type { StatutValidation, ValidationFinance } from "../api";
import { useDeciderValidation, useValidations } from "../hooks";
import { CHAMP, ErreurLecture } from "./communs";

const STATUTS: Record<StatutValidation, { libelle: string; ton: "orange" | "vert" | "gris" | "rouge" }> = {
  en_attente: { libelle: "En attente", ton: "orange" },
  executee: { libelle: "Validée et exécutée", ton: "vert" },
  refusee: { libelle: "Refusée", ton: "gris" },
  echouee: { libelle: "Validée, échec", ton: "rouge" },
};
const FILTRES = [["en_attente", "En attente"], ["", "Toutes"], ["executee", "Exécutées"], ["refusee", "Refusées"], ["echouee", "En échec"]] as const;

function heure(iso: string) {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Double validation (GL-10): every money operation from the threshold (a refund decided in the back-office, a payout
 * due to a host) waits here for a second person. The person who asked can never approve; when the system asked, two
 * different people must approve. The last approval runs the operation.
 */
export default function Validations() {
  const [statut, setStatut] = useState("en_attente");
  const { data, isLoading, isError, error } = useValidations(statut);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {FILTRES.map(([code, libelle]) => (
          <button key={code} onClick={() => setStatut(code)} aria-pressed={statut === code}
            className={cn("px-3 py-1.5 rounded-lg text-sm font-semibold border",
              statut === code ? "border-primary text-brand bg-primary/5" : "border-gray-200 text-dark hover:bg-gray-50")}>
            {libelle}
          </button>
        ))}
        {data && (
          <p className="text-sm text-muted sm:ml-auto">
            {data.seuil ? `Deux personnes à partir de ${formatPrice(data.seuil)}` : "Aucun seuil décidé : la double validation est inactive"}
          </p>
        )}
      </div>
      {data && !data.peut_operer && (
        <p className="text-sm bg-amber-50 text-amber-900 rounded-xl px-4 py-3">
          Consultation seulement : décider demande la permission « Opérations financières » (donnée par un super administrateur).
        </p>
      )}

      {isLoading && <div className="h-48 skeleton rounded-2xl" />}
      {isError && <ErreurLecture erreur={error} />}
      {data?.validations.length === 0 && (
        <p className="bg-surface rounded-2xl border border-gray-100 p-8 text-center text-muted">
          <ShieldCheck size={28} className="mx-auto mb-2 text-gray-300" aria-hidden />
          {statut === "en_attente" ? "Rien n'attend de validation." : "Aucune demande."}
        </p>
      )}
      <ul className="space-y-3">
        {data?.validations.map((v) => <Demande key={v.id} v={v} peutOperer={data.peut_operer} />)}
      </ul>
    </div>
  );
}

function Demande({ v, peutOperer }: { v: ValidationFinance; peutOperer: boolean }) {
  const decider = useDeciderValidation();
  const [refus, setRefus] = useState<string | null>(null);
  const reference = v.donnees.reference || v.donnees.beneficiaire || "";

  const agir = (decision: "approuver" | "refuser") => decider.mutate({ id: v.id, decision, motif: refus ?? "" }, {
    onSuccess: (resultat) => {
      setRefus(null);
      if (resultat.statut === "en_attente") toast.success("Première validation enregistrée : une deuxième personne doit confirmer.");
      else if (resultat.statut === "executee") toast.success(resultat.resultat || "Opération validée et exécutée.");
      else if (resultat.statut === "echouee") toast.error(`Validée mais en échec : ${resultat.resultat}`);
      else toast.success("Demande refusée.");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Décision impossible.")),
  });

  return (
    <li className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-dark">{v.operation_libelle}{reference && <span className="text-muted font-normal"> · {reference}</span>}</p>
          <p className="text-sm text-muted">{v.motif || "—"}</p>
        </div>
        <div className="text-right">
          <p className="font-heading font-bold text-lg tabular-nums">{formatPrice(v.montant)}</p>
          <Pill ton={STATUTS[v.statut].ton}>{STATUTS[v.statut].libelle}</Pill>
        </div>
      </div>
      <ol className="text-xs text-muted space-y-0.5">
        <li>Demandée par <strong className="text-dark">{v.demandee_par || "—"}</strong> le {formatDate(v.demandee_le)} à {heure(v.demandee_le)}</li>
        {v.premiere_par && <li>Première validation : <strong className="text-dark">{v.premiere_par}</strong></li>}
        {v.decidee_par && v.decidee_le && (
          <li>{v.statut === "refusee" ? "Refusée" : "Validée"} par <strong className="text-dark">{v.decidee_par}</strong> le {formatDate(v.decidee_le)} à {heure(v.decidee_le)}</li>
        )}
        {v.resultat && <li className={v.statut === "echouee" ? "text-red-700" : ""}>{v.resultat}</li>}
      </ol>

      {v.statut === "en_attente" && peutOperer && (
        v.je_peux_valider ? (
          <div className="flex flex-col sm:flex-row sm:items-end gap-2 pt-1">
            {refus === null ? (
              <>
                <button onClick={() => agir("approuver")} disabled={decider.isPending}
                  className="flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-bold disabled:opacity-50">
                  <Check size={16} aria-hidden /> {v.demandee_par === "Système" && !v.premiere_par ? "Première validation" : "Valider et exécuter"}
                </button>
                <button onClick={() => setRefus("")} className="flex items-center justify-center gap-2 px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">
                  <X size={16} aria-hidden /> Refuser
                </button>
              </>
            ) : (
              <>
                <label className="text-sm flex-1"><span className="block text-xs font-semibold text-muted mb-1">Motif du refus</span>
                  <input className={cn(CHAMP, "w-full")} value={refus} onChange={(e) => setRefus(e.target.value)} maxLength={500} autoFocus /></label>
                <button onClick={() => agir("refuser")} disabled={refus.trim().length < 5 || decider.isPending}
                  className="px-4 py-2 rounded-xl bg-red-700 text-white text-sm font-bold disabled:opacity-50">Refuser</button>
                <button onClick={() => setRefus(null)} className="px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Annuler</button>
              </>
            )}
          </div>
        ) : <p className="text-sm text-muted">Vous avez déjà donné votre accord : une autre personne doit valider.</p>
      )}
    </li>
  );
}
