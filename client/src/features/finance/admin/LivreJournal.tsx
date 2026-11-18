"use client";

import { useState } from "react";
import { CheckCircle2, TriangleAlert } from "lucide-react";
import { Pagination } from "@/components/backoffice/AdminTable";
import { formatDate, formatPrice } from "@/lib/utils";
import { urlExportEcritures } from "../api";
import { useLivreJournal, useReferentielsFinance } from "../hooks";
import { BoutonTelecharger, ChoixCode, ErreurLecture, Periode, Somme, moisEnCours } from "./communs";

/**
 * The journal (AUDCIF art. 19, GL-3): every movement as two entries of the same amount, one in debit and one in
 * credit, in date order. Its two totals are always equal; otherwise there is a bug in the ledger.
 */
export default function LivreJournal() {
  const [{ debut, fin }, setPeriode] = useState(moisEnCours);
  const [journal, setJournal] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, isFetching, isError, error } = useLivreJournal(debut, fin, journal, page);
  const { data: ref } = useReferentielsFinance();
  const equilibre = data && data.totaux.total_debit === data.totaux.total_credit;

  return (
    <div className="space-y-4">
      <Periode debut={debut} fin={fin} onChange={(d, f) => { setPeriode({ debut: d, fin: f }); setPage(1); }}>
        <div className="sm:w-56"><ChoixCode libelle="Journal" valeur={journal} onChange={(v) => { setJournal(v); setPage(1); }} options={ref?.journaux ?? []} /></div>
        <div className="sm:ml-auto"><BoutonTelecharger url={urlExportEcritures(debut, fin)} nom="kwaba-ecritures.csv" libelle="Export comptable (CSV)" disabled={!data} /></div>
      </Periode>

      {isLoading && <div className="h-64 skeleton rounded-2xl" />}
      {isError && <ErreurLecture erreur={error} />}
      {data && (
        <>
          <div className={`flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border px-4 py-3 text-sm ${equilibre ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
            <span className="flex items-center gap-2 font-semibold text-dark">
              {equilibre ? <CheckCircle2 size={18} className="text-emerald-700" aria-hidden /> : <TriangleAlert size={18} className="text-red-700" aria-hidden />}
              {equilibre ? "Débits égaux aux crédits" : "Débits et crédits différents : à signaler"}
            </span>
            <span className="tabular-nums">Total débit <strong>{formatPrice(data.totaux.total_debit)}</strong></span>
            <span className="tabular-nums">Total crédit <strong>{formatPrice(data.totaux.total_credit)}</strong></span>
            <span className="text-muted">{data.count} écriture{data.count > 1 ? "s" : ""}</span>
          </div>

          <section className={`bg-surface rounded-2xl border border-gray-100 overflow-x-auto transition-opacity ${isFetching ? "opacity-60" : ""}`}>
            <table className="w-full text-sm min-w-[760px]">
              <thead><tr className="text-left text-xs text-muted border-b border-gray-100">
                <th className="px-4 py-2 font-semibold">Date</th><th className="px-3 py-2 font-semibold">Jnl</th>
                <th className="px-3 py-2 font-semibold">N°</th><th className="px-3 py-2 font-semibold">Compte</th>
                <th className="px-3 py-2 font-semibold">Libellé</th><th className="px-3 py-2 font-semibold">Pièce</th>
                <th className="px-3 py-2 font-semibold text-right">Débit</th><th className="px-4 py-2 font-semibold text-right">Crédit</th>
              </tr></thead>
              <tbody>
                {data.results.length === 0 && <tr><td colSpan={8} className="px-4 py-6 text-center text-muted">Aucune écriture sur la période.</td></tr>}
                {data.results.map((e) => (
                  <tr key={`${e.mouvement_id}-${e.ligne_ecriture}`}
                    className={`align-top ${e.ligne_ecriture === 2 ? "border-b border-gray-100" : ""}`}>
                    <td className="px-4 py-1.5 whitespace-nowrap">{e.ligne_ecriture === 1 ? formatDate(e.date_ecriture) : ""}</td>
                    <td className="px-3 py-1.5 text-muted">{e.journal}</td>
                    <td className="px-3 py-1.5 text-muted tabular-nums">{e.mouvement_id}</td>
                    <td className="px-3 py-1.5 tabular-nums whitespace-nowrap">
                      {e.compte_general}{e.compte_auxiliaire && <span className="block text-xs text-muted truncate max-w-40" title={e.compte_auxiliaire}>{e.compte_auxiliaire}</span>}
                    </td>
                    <td className={`px-3 py-1.5 ${e.credit ? "pl-8" : ""}`}>{e.libelle}</td>
                    <td className="px-3 py-1.5 text-muted whitespace-nowrap">{e.piece ?? ""}</td>
                    <td className="px-3 py-1.5 text-right"><Somme montant={e.debit} /></td>
                    <td className="px-4 py-1.5 text-right"><Somme montant={e.credit} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <Pagination page={page} count={data.count} pageSize={data.page_size} onChange={setPage} />
        </>
      )}
    </div>
  );
}
