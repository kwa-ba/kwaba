"use client";

import { CheckCircle2, TriangleAlert } from "lucide-react";
import { formatPrice } from "@/lib/utils";
import { useGrandLivre, usePilotage } from "../hooks";
import Actualiser from "./Actualiser";
import { libelleMois, moisEnCours } from "./communs";
import { OFFRES, TIERS } from "./libelles";

function Chiffre({ libelle, montant, aide, accent }: { libelle: string; montant: number; aide: string; accent?: boolean }) {
  return (
    <div className={`rounded-2xl p-4 ${accent ? "bg-primary text-white" : "bg-surface border border-gray-100"}`}>
      <p className={`text-xs font-semibold ${accent ? "text-white/80" : "text-muted"}`}>{libelle}</p>
      <p className="font-heading font-bold text-xl mt-1 tabular-nums">{formatPrice(montant)}</p>
      <p className={`text-xs mt-0.5 ${accent ? "text-white/80" : "text-muted"}`}>{aide}</p>
    </div>
  );
}

/** Margin by offer, real payment fee rate and guarantee fund of the current month (FIN-12). */
function PilotageDuMois() {
  const mois = moisEnCours().debut.slice(0, 7);
  const { data } = usePilotage(mois);
  if (!data) return null;
  const taux = data.taux_frais_reel;
  return (
    <section className="bg-background rounded-2xl border border-gray-100 p-5">
      <h2 className="font-heading font-bold text-dark">Pilotage du mois</h2>
      <p className="text-xs text-muted mb-3 capitalize">{libelleMois(data.mois)}</p>
      <div className="grid sm:grid-cols-2 gap-3 mb-4 text-sm">
        <div className="rounded-xl bg-surface border border-gray-100 px-4 py-3">
          <p className="text-xs font-semibold text-muted">Taux de frais de paiement réel</p>
          <p className="font-heading font-bold text-lg tabular-nums">{taux?.pct_du_revenu != null ? `${taux.pct_du_revenu.toLocaleString("fr-FR")} % du revenu` : "—"}</p>
          <p className="text-xs text-muted">{taux ? `${formatPrice(taux.frais)} de frais sur ${formatPrice(taux.volume_encaisse)} encaissés` : "Aucun frais enregistré ce mois-ci"}</p>
        </div>
        <div className="rounded-xl bg-surface border border-gray-100 px-4 py-3">
          <p className="text-xs font-semibold text-muted">Fonds de garantie</p>
          <p className="font-heading font-bold text-lg tabular-nums">{formatPrice(Math.abs(data.fonds_garantie))}</p>
          <p className="text-xs text-muted">Réserve mise de côté : jamais de l&apos;argent libre</p>
        </div>
      </div>
      {data.marge_par_offre.length === 0 ? <p className="text-sm text-muted">Aucune recette ce mois-ci.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted border-b border-gray-100">
              <th className="py-2 pr-3 font-semibold">Offre</th><th className="py-2 px-3 font-semibold text-right">Recettes</th>
              <th className="py-2 px-3 font-semibold text-right">Charges variables</th><th className="py-2 pl-3 font-semibold text-right">Marge</th>
            </tr></thead>
            <tbody className="tabular-nums">
              {data.marge_par_offre.map((m) => (
                <tr key={m.offre_code} className="border-b border-gray-50 last:border-0">
                  <td className="py-2 pr-3">{OFFRES[m.offre_code] ?? m.offre_code}</td>
                  <td className="py-2 px-3 text-right">{formatPrice(m.recettes)}</td>
                  <td className="py-2 px-3 text-right">{formatPrice(m.charges_variables)}</td>
                  <td className={`py-2 pl-3 text-right font-semibold ${m.marge < 0 ? "text-red-700" : ""}`}>{formatPrice(m.marge)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/**
 * First page of the Finance heading: the invariants that must always hold, the balances that never mix (Kwa-Ba's
 * revenue, money owed to partners and travellers, deposits held), each money account and the sums owed by partner.
 * Every figure is read from the ledger, none is computed again from the bookings.
 */
export default function SyntheseFinance() {
  const { data: d, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useGrandLivre();
  const anomalies = d?.invariants.filter((i) => i.anomalies > 0) ?? [];

  return (
    <div className="space-y-6">
      <Actualiser lu={d ? dataUpdatedAt : undefined} enCours={isFetching} onActualiser={() => refetch()} />

      {isLoading && <div className="h-64 skeleton rounded-2xl" />}
      {isError && <p className="text-sm text-red-700">Impossible de lire le grand livre.</p>}
      {d && (
        <>
          <section className={`rounded-2xl border p-5 ${anomalies.length ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"}`}>
            <div className="flex items-center gap-2 mb-3">
              {anomalies.length
                ? <TriangleAlert size={20} className="text-red-700" aria-hidden />
                : <CheckCircle2 size={20} className="text-emerald-700" aria-hidden />}
              <h2 className="font-heading font-bold text-dark">
                {anomalies.length ? `${anomalies.length} invariant${anomalies.length > 1 ? "s" : ""} en anomalie` : "Tous les invariants sont respectés"}
              </h2>
            </div>
            <ul className="grid sm:grid-cols-2 gap-2 text-sm">
              {d.invariants.map((i) => (
                <li key={i.invariant} className={`flex items-start justify-between gap-3 rounded-xl px-3 py-2 ${i.anomalies ? "bg-surface text-red-800 font-semibold" : "bg-surface/70 text-dark"}`}>
                  <span><span className="text-muted font-normal">{i.invariant}</span> · {i.libelle}</span>
                  <span className="tabular-nums whitespace-nowrap">{i.anomalies ? `${i.anomalies} anomalie${i.anomalies > 1 ? "s" : ""}` : "OK"}</span>
                </li>
              ))}
            </ul>
          </section>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Chiffre libelle="Revenu Kwa-Ba du mois" montant={d.soldes.revenu_du_mois} aide="Frais de service et commissions acquises" accent />
            <Chiffre libelle="Dû aux partenaires" montant={d.soldes.du_partenaires} aide="Fonds de tiers : jamais à Kwa-Ba" />
            <Chiffre libelle="Dû aux voyageurs" montant={d.soldes.du_voyageurs} aide="Remboursements décidés, pas encore envoyés" />
            <Chiffre libelle="Cautions détenues" montant={d.soldes.cautions_detenues} aide="Argent des voyageurs, à restituer" />
          </div>
          {Object.keys(d.soldes.comptes).length > 0 && (
            <p className="text-sm text-muted">
              Solde au grand livre : {Object.entries(d.soldes.comptes).map(([c, m]) => `${c === "FEDAPAY" ? "FedaPay" : c} ${formatPrice(m)}`).join(" · ")}
            </p>
          )}

          <PilotageDuMois />

          <section className="bg-background rounded-2xl border border-gray-100 p-5">
            <h2 className="font-heading font-bold text-dark mb-3">Sommes dues, par partenaire</h2>
            {d.du_aux_partenaires.length === 0 ? <p className="text-sm text-muted">Kwa-Ba ne doit rien à personne.</p> : (
              <ul className="divide-y divide-gray-50 text-sm">
                {d.du_aux_partenaires.map((p) => (
                  <li key={`${p.tiers_type}-${p.tiers_id}`} className="flex flex-wrap justify-between gap-2 py-2">
                    <span className="min-w-0">
                      <strong className="text-dark">{p.nom || p.tiers_id || "À désigner"}</strong> <span className="text-muted">· {TIERS[p.tiers_type] ?? p.tiers_type}</span>
                      {p.email && <span className="block text-xs text-muted break-all">{p.email}</span>}
                    </span>
                    <span className={`tabular-nums font-semibold ${p.solde_du < 0 ? "text-red-700" : "text-dark"}`}>{formatPrice(p.solde_du)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
