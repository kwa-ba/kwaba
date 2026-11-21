"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatPrice } from "@/lib/utils";
import { urlExportRapport, type DemandeRapport } from "../api";
import { useCreerRapport, useRapports, useReferentielsFinance, useResultatRapport } from "../hooks";
import { BoutonTelecharger, CHAMP, ChoixCode, ErreurLecture, Periode, moisEnCours } from "./communs";

const PERIODICITES: Record<string, string> = { mensuel: "Mensuel", quotidien: "Quotidien", annuel: "Annuel" };
const DESTINATAIRES: Record<string, string> = { associes: "Associés", dirigeants: "Dirigeants", cabinet: "Cabinet comptable" };

/** « Frais par moyen » → « frais_par_moyen » (code of a new report). */
function codeDe(titre: string): string {
  return titre.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
}

/**
 * Reports (GL-19, FIN-17): the saved reports, and a free report on one or two axes with filters. A report that is
 * useful can be saved: a new report is a row, never a development. Every amount is read from the ledger, signed (an
 * expense is negative).
 */
export default function Rapports() {
  const [{ debut, fin }, setPeriode] = useState(moisEnCours);
  const { data: liste, isError: erreurListe, error } = useRapports();
  const { data: ref } = useReferentielsFinance();
  const [demande, setDemande] = useState<DemandeRapport | null>({ code: "recettes_type" });
  const [libre, setLibre] = useState<{ axe1: string; axe2: string; famille: string; offre: string }>({ axe1: "mois", axe2: "", famille: "", offre: "" });
  const resultat = useResultatRapport(demande, debut, fin);
  const creer = useCreerRapport();
  const [titre, setTitre] = useState("");

  const demandeLibre = (): DemandeRapport => ({
    axe1: libre.axe1, axe2: libre.axe2 || undefined,
    familles: libre.famille ? [libre.famille] : undefined, offres: libre.offre ? [libre.offre] : undefined,
  });
  const axes = liste?.axes ?? [];
  const libelleAxe = (code: string | null | undefined) => axes.find((a) => a.code === code)?.libelle ?? code ?? "";
  const rapportChoisi = demande?.code ? liste?.rapports.find((r) => r.code === demande.code) : undefined;

  const enregistrer = () => creer.mutate({
    code: codeDe(titre), titre: titre.trim(), axe1: libre.axe1, axe2: libre.axe2 || null,
    familles: libre.famille ? [libre.famille] : undefined, offres: libre.offre ? [libre.offre] : undefined,
  }, {
    onSuccess: (r) => { toast.success(`Rapport « ${r.titre} » enregistré.`); setTitre(""); setDemande({ code: r.code }); },
    onError: (err) => toast.error(apiErrorMessage(err, "Enregistrement impossible.")),
  });

  return (
    <div className="grid lg:grid-cols-[18rem_1fr] gap-5 items-start">
      <section className="bg-surface rounded-2xl border border-gray-100 p-3" aria-label="Rapports enregistrés">
        <h2 className="font-heading font-bold text-dark px-2 pt-1 pb-2">Rapports enregistrés</h2>
        {erreurListe && <ErreurLecture erreur={error} />}
        <ul className="space-y-0.5">
          {liste?.rapports.map((r) => (
            <li key={r.code}>
              <button onClick={() => setDemande({ code: r.code })} aria-pressed={demande?.code === r.code}
                className={cn("w-full text-left px-2 py-2 rounded-lg text-sm", demande?.code === r.code ? "bg-primary/10 text-brand dark:bg-gray-100 dark:text-dark" : "hover:bg-gray-50")}>
                <span className="font-medium">{r.titre}</span>
                <span className="block text-xs text-muted">
                  {[r.periodicite && PERIODICITES[r.periodicite], r.destinataire && (DESTINATAIRES[r.destinataire] ?? r.destinataire)].filter(Boolean).join(" · ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div className="space-y-4 min-w-0">
        <Periode debut={debut} fin={fin} onChange={(d, f) => setPeriode({ debut: d, fin: f })}>
          {demande && <div className="sm:ml-auto"><BoutonTelecharger url={urlExportRapport(demande, debut, fin)} nom="kwaba-rapport.csv" libelle="Export CSV" disabled={!resultat.data} /></div>}
        </Periode>

        <section className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-3" aria-label="Rapport libre">
          <h2 className="font-heading font-bold text-dark">Rapport libre</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <ChoixCode libelle="Regrouper par" valeur={libre.axe1 === "mois" ? "" : libre.axe1} onChange={(v) => setLibre((l) => ({ ...l, axe1: v || "mois" }))}
              options={axes.filter((a) => a.code !== "mois")} tous="Mois comptable" />
            <ChoixCode libelle="Puis par" valeur={libre.axe2} onChange={(v) => setLibre((l) => ({ ...l, axe2: v }))} options={axes.filter((a) => a.code !== libre.axe1)} tous="Aucun" />
            <ChoixCode libelle="Famille" valeur={libre.famille} onChange={(v) => setLibre((l) => ({ ...l, famille: v }))} options={ref?.familles ?? []} tous="Toutes" />
            <ChoixCode libelle="Offre" valeur={libre.offre} onChange={(v) => setLibre((l) => ({ ...l, offre: v }))} options={ref?.offres ?? []} tous="Toutes" />
          </div>
          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            <button onClick={() => setDemande(demandeLibre())} className="px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-bold">Afficher</button>
            <label className="text-sm flex-1 min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Enregistrer ce rapport sous le titre</span>
              <input className={cn(CHAMP, "w-full")} value={titre} maxLength={120} onChange={(e) => setTitre(e.target.value)} placeholder="Ex. Dépenses par mois et par offre" /></label>
            <button onClick={enregistrer} disabled={titre.trim().length < 3 || creer.isPending}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 bg-surface text-sm font-semibold disabled:opacity-50">
              <Save size={16} aria-hidden /> {creer.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
        </section>

        {resultat.isLoading && <div className="h-48 skeleton rounded-2xl" />}
        {resultat.isError && <ErreurLecture erreur={resultat.error} />}
        {resultat.data && (
          <section className="bg-surface rounded-2xl border border-gray-100 overflow-x-auto">
            <h2 className="font-heading font-bold text-dark px-5 pt-5">{resultat.data.titre}</h2>
            <p className="text-xs text-muted px-5 mb-3">
              {rapportChoisi ? `Par ${libelleAxe(rapportChoisi.axe1).toLowerCase()}${rapportChoisi.axe2 ? `, puis par ${libelleAxe(rapportChoisi.axe2).toLowerCase()}` : ""}` : "Montants signés : une sortie est négative."}
            </p>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-muted border-b border-gray-100">
                <th className="px-5 py-2 font-semibold">{libelleAxe(rapportChoisi?.axe1 ?? demande?.axe1) || "Axe"}</th>
                {(rapportChoisi?.axe2 ?? demande?.axe2) && <th className="px-3 py-2 font-semibold">{libelleAxe(rapportChoisi?.axe2 ?? demande?.axe2)}</th>}
                <th className="px-3 py-2 font-semibold text-right">Lignes</th><th className="px-5 py-2 font-semibold text-right">Montant</th>
              </tr></thead>
              <tbody className="tabular-nums">
                {resultat.data.lignes.length === 0 && <tr><td colSpan={4} className="px-5 py-6 text-center text-muted">Aucune ligne sur la période.</td></tr>}
                {resultat.data.lignes.map((l, i) => (
                  <tr key={`${l.axe1}-${l.axe2}-${i}`} className="border-b border-gray-50 last:border-0">
                    <td className="px-5 py-2">{l.axe1 ?? "—"}</td>
                    {(rapportChoisi?.axe2 ?? demande?.axe2) && <td className="px-3 py-2">{l.axe2 ?? "—"}</td>}
                    <td className="px-3 py-2 text-right text-muted">{l.nb}</td>
                    <td className={cn("px-5 py-2 text-right font-semibold", l.montant < 0 && "text-red-700")}>{formatPrice(l.montant)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>
    </div>
  );
}
