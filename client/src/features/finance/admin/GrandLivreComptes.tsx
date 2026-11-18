"use client";

import { useState } from "react";
import { Pagination } from "@/components/backoffice/AdminTable";
import { cn, formatDate } from "@/lib/utils";
import { useAuxiliaires, useComptes, useGrandLivreCompte } from "../hooks";
import { CHAMP, ErreurLecture, Periode, Solde, Somme, moisEnCours } from "./communs";

function Case({ libelle, accent, children }: { libelle: string; accent?: boolean; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-2xl p-4 border", accent ? "border-primary/30 bg-primary/5" : "border-gray-100 bg-surface")}>
      <p className="text-xs font-semibold text-muted">{libelle}</p>
      <p className="font-heading font-bold text-lg mt-1">{children}</p>
    </div>
  );
}

/**
 * The general ledger by account (AUDCIF art. 19, GL-4): choose an account (FedaPay, a host's account…) and see its
 * entries with the balance after each one. Answers « how much do we owe this host? » and « how much is on FedaPay? ».
 * A result account (classes 6, 7, 8) starts each financial year at zero.
 */
export default function GrandLivreComptes() {
  const [{ debut, fin }, setPeriode] = useState(moisEnCours);
  const [compte, setCompte] = useState("");
  const [auxiliaire, setAuxiliaire] = useState("");
  const [page, setPage] = useState(1);
  const comptes = useComptes();
  const auxiliaires = useAuxiliaires(compte);
  const { data, isLoading, isFetching, isError, error } = useGrandLivreCompte(compte, auxiliaire, debut, fin, page);
  const choisi = comptes.data?.find((c) => c.compte_general === compte);

  const choisir = (c: string) => { setCompte(c); setAuxiliaire(""); setPage(1); };

  return (
    <div className="grid lg:grid-cols-[18rem_1fr] gap-5 items-start">
      <section className="bg-surface rounded-2xl border border-gray-100 p-3" aria-label="Comptes">
        <h2 className="font-heading font-bold text-dark px-2 pt-1 pb-2">Comptes mouvementés</h2>
        {comptes.isLoading && <div className="h-40 skeleton rounded-xl" />}
        {comptes.isError && <ErreurLecture erreur={comptes.error} />}
        {comptes.data?.length === 0 && <p className="text-sm text-muted px-2 pb-2">Aucune écriture pour l&apos;instant.</p>}
        {/* Phone: a select keeps the page short */}
        {!!comptes.data?.length && (
          <select className={cn(CHAMP, "w-full lg:hidden")} value={compte} onChange={(e) => choisir(e.target.value)} aria-label="Compte">
            <option value="">Choisir un compte</option>
            {comptes.data.map((c) => <option key={c.compte_general} value={c.compte_general}>{c.compte_general} · {c.libelle}</option>)}
          </select>
        )}
        <ul className="hidden lg:block space-y-0.5 max-h-[32rem] overflow-y-auto">
          {comptes.data?.map((c) => (
            <li key={c.compte_general}>
              <button onClick={() => choisir(c.compte_general)} aria-pressed={compte === c.compte_general}
                className={cn("w-full text-left px-2 py-2 rounded-lg text-sm flex justify-between gap-2",
                  compte === c.compte_general ? "bg-primary/10 text-brand dark:bg-gray-100 dark:text-dark" : "hover:bg-gray-50")}>
                <span className="min-w-0"><strong className="tabular-nums">{c.compte_general}</strong>
                  <span className="block text-xs text-muted truncate">{c.libelle || "Sans libellé"}</span></span>
                <Solde solde={c.solde} className="text-xs" />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div className="space-y-4 min-w-0">
        <Periode debut={debut} fin={fin} onChange={(d, f) => { setPeriode({ debut: d, fin: f }); setPage(1); }}>
          {!!auxiliaires.data?.length && (
            <label className="text-sm min-w-0 sm:w-72"><span className="block text-xs font-semibold text-muted mb-1">Tiers (compte auxiliaire)</span>
              <select className={cn(CHAMP, "w-full")} value={auxiliaire} onChange={(e) => { setAuxiliaire(e.target.value); setPage(1); }}>
                <option value="">Tous les tiers du compte</option>
                {auxiliaires.data.map((a) => <option key={a.compte_auxiliaire} value={a.compte_auxiliaire}>{a.nom || a.compte_auxiliaire}</option>)}
              </select>
            </label>
          )}
        </Periode>

        {!compte && <p className="bg-surface rounded-2xl border border-gray-100 p-8 text-center text-muted">Choisissez un compte pour voir ses écritures et son solde.</p>}
        {compte && isLoading && <div className="h-64 skeleton rounded-2xl" />}
        {compte && isError && <ErreurLecture erreur={error} />}
        {compte && data && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <Case libelle="Solde d'ouverture"><Solde solde={data.solde_ouverture} /></Case>
              <Case libelle="Total débit"><Somme montant={data.total_debit} /></Case>
              <Case libelle="Total crédit"><Somme montant={data.total_credit} /></Case>
              <Case libelle="Solde de clôture" accent><Solde solde={data.solde_cloture} /></Case>
            </div>
            {choisi && <p className="text-sm text-muted">{choisi.compte_general} · {choisi.libelle}{auxiliaire && ` · ${auxiliaires.data?.find((a) => a.compte_auxiliaire === auxiliaire)?.nom || auxiliaire}`}</p>}

            <section className={cn("bg-surface rounded-2xl border border-gray-100 overflow-x-auto transition-opacity", isFetching && "opacity-60")}>
              <table className="w-full text-sm min-w-[720px]">
                <thead><tr className="text-left text-xs text-muted border-b border-gray-100">
                  <th className="px-4 py-2 font-semibold">Date</th><th className="px-3 py-2 font-semibold">Jnl</th>
                  <th className="px-3 py-2 font-semibold">Libellé</th><th className="px-3 py-2 font-semibold">Pièce</th>
                  <th className="px-3 py-2 font-semibold text-right">Débit</th><th className="px-3 py-2 font-semibold text-right">Crédit</th>
                  <th className="px-4 py-2 font-semibold text-right">Solde</th>
                </tr></thead>
                <tbody>
                  {data.results.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-muted">Aucune écriture sur la période.</td></tr>}
                  {data.results.map((e) => (
                    <tr key={`${e.mouvement_id}-${e.ligne_ecriture}`} className="border-b border-gray-50 last:border-0 align-top">
                      <td className="px-4 py-2 whitespace-nowrap">{formatDate(e.date_ecriture)}</td>
                      <td className="px-3 py-2 text-muted">{e.journal}</td>
                      <td className="px-3 py-2">{e.libelle}{!auxiliaire && e.compte_auxiliaire && <span className="block text-xs text-muted truncate max-w-64">{e.compte_auxiliaire}</span>}</td>
                      <td className="px-3 py-2 text-muted whitespace-nowrap">{e.piece ?? ""}</td>
                      <td className="px-3 py-2 text-right"><Somme montant={e.debit} /></td>
                      <td className="px-3 py-2 text-right"><Somme montant={e.credit} /></td>
                      <td className="px-4 py-2 text-right"><Solde solde={e.solde_progressif} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <Pagination page={page} count={data.count} pageSize={data.page_size} onChange={setPage} />
            <p className="text-xs text-muted">D : solde débiteur (ce que le compte détient ou ce qu&apos;on nous doit). C : solde créditeur (ce que Kwa-Ba doit, ou un produit).</p>
          </>
        )}
      </div>
    </div>
  );
}
