"use client";

import { useState } from "react";
import { CheckCircle2, TriangleAlert } from "lucide-react";
import { formatPrice } from "@/lib/utils";
import { urlExportEcritures } from "../api";
import { useBalance } from "../hooks";
import { BoutonTelecharger, ErreurLecture, Periode, Solde, Somme, moisEnCours } from "./communs";

/**
 * The trial balance (AUDCIF art. 19, GL-5): for each account, its opening balance, what came in and out over the
 * period, and its closing balance. Total debits equal total credits: the overall check of the books.
 */
export default function BalanceGenerale() {
  const [{ debut, fin }, setPeriode] = useState(moisEnCours);
  const { data, isLoading, isError, error } = useBalance(debut, fin);

  return (
    <div className="space-y-4">
      <Periode debut={debut} fin={fin} onChange={(d, f) => setPeriode({ debut: d, fin: f })}>
        <div className="sm:ml-auto"><BoutonTelecharger url={urlExportEcritures(debut, fin)} nom="kwaba-ecritures.csv" libelle="Export comptable (CSV)" disabled={!data} /></div>
      </Periode>

      {isLoading && <div className="h-64 skeleton rounded-2xl" />}
      {isError && <ErreurLecture erreur={error} />}
      {data && (
        <>
          <div className={`flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border px-4 py-3 text-sm ${data.equilibree ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
            <span className="flex items-center gap-2 font-semibold text-dark">
              {data.equilibree ? <CheckCircle2 size={18} className="text-emerald-700" aria-hidden /> : <TriangleAlert size={18} className="text-red-700" aria-hidden />}
              {data.equilibree ? "Balance équilibrée" : `Balance déséquilibrée de ${formatPrice(Math.abs(data.totaux.total_debit - data.totaux.total_credit))} : à signaler`}
            </span>
            <span className="tabular-nums">Débits de la période <strong>{formatPrice(data.totaux.total_debit)}</strong></span>
            <span className="tabular-nums">Crédits de la période <strong>{formatPrice(data.totaux.total_credit)}</strong></span>
          </div>

          <section className="bg-surface rounded-2xl border border-gray-100 overflow-x-auto">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="text-left text-xs text-muted border-b border-gray-100">
                  <th className="px-4 py-2 font-semibold">Compte</th><th className="px-3 py-2 font-semibold">Libellé</th>
                  <th className="px-3 py-2 font-semibold text-right">Solde d&apos;ouverture</th>
                  <th className="px-3 py-2 font-semibold text-right">Débit</th><th className="px-3 py-2 font-semibold text-right">Crédit</th>
                  <th className="px-4 py-2 font-semibold text-right">Solde de clôture</th>
                </tr>
              </thead>
              <tbody>
                {data.comptes.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-muted">Aucune écriture jusqu&apos;à cette date.</td></tr>}
                {data.comptes.map((c) => (
                  <tr key={c.compte_general} className="border-b border-gray-50 last:border-0">
                    <td className="px-4 py-2 font-semibold tabular-nums">{c.compte_general}</td>
                    <td className="px-3 py-2">{c.libelle || <span className="text-muted">Sans libellé</span>}</td>
                    <td className="px-3 py-2 text-right"><Solde solde={c.solde_ouverture} /></td>
                    <td className="px-3 py-2 text-right"><Somme montant={c.total_debit} /></td>
                    <td className="px-3 py-2 text-right"><Somme montant={c.total_credit} /></td>
                    <td className="px-4 py-2 text-right"><Solde solde={c.solde_cloture} /></td>
                  </tr>
                ))}
              </tbody>
              {data.comptes.length > 0 && (
                <tfoot><tr className="border-t-2 border-gray-200 font-bold">
                  <td className="px-4 py-2" colSpan={3}>Totaux</td>
                  <td className="px-3 py-2 text-right"><Somme montant={data.totaux.total_debit} /></td>
                  <td className="px-3 py-2 text-right"><Somme montant={data.totaux.total_credit} /></td>
                  <td className="px-4 py-2" />
                </tr></tfoot>
              )}
            </table>
          </section>
          <p className="text-xs text-muted">
            Les comptes de bilan (classes 1 à 5) reprennent leur solde depuis la première écriture ; les comptes de résultat (classes 6, 7 et 8)
            repartent de zéro au 1er janvier. Les numéros de comptes sont à valider par l&apos;expert-comptable.
          </p>
        </>
      )}
    </div>
  );
}
