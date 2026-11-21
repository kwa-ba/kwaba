"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Calculator, ShieldCheck } from "lucide-react";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import type { DotationFonds, FondsGarantie as Fonds, SinistreFonds } from "../api";
import { useAnnulerSinistre, useDoterFondsGarantie, useFondsGarantie, useImputerSinistre } from "../hooks";
import { CHAMP, ErreurLecture, libelleMois } from "./communs";

function etatDotation(d: DotationFonds): { libelle: string; ton: "vert" | "orange" | "gris" | "bleu" } {
  if (!d.termine) return { libelle: "Mois en cours", ton: "gris" };
  if (d.ecrite < d.due) return { libelle: "À écrire", ton: "orange" };
  if (d.etat === "verrouillee") return { libelle: "Clôturé", ton: "bleu" };
  return { libelle: "À jour", ton: "vert" };
}

const pourcent = (taux: number | string) => `${Number(taux).toLocaleString("fr-FR")} %`;

/**
 * Guarantee fund (GL-17): a reserve kept apart from the free money, outside the result (ADR-031). Each finished month, its rate of the month's net
 * revenue is allocated to it (each night, at the closing, or with the button); a loss Kwa-Ba pays under its guarantee
 * (a D04 expense) is covered by the fund with the reference of the decision. Below its target, the finance team is
 * alerted.
 */
export default function FondsGarantie() {
  const { data, isLoading, isError, error } = useFondsGarantie();
  const doter = useDoterFondsGarantie();
  const annuler = useAnnulerSinistre();
  const [couvrir, setCouvrir] = useState(false);

  if (isLoading) return <div className="h-40 skeleton rounded-2xl" />;
  if (isError || !data) return <ErreurLecture erreur={error} />;

  const aEcrire = data.dotations.filter((d) => d.termine && d.etat !== "verrouillee" && d.ecrite < d.due);
  const calculer = () => doter.mutate(undefined, {
    onSuccess: (r) => toast.success(r.ajoute ? `${formatPrice(r.ajoute)} dotés au fonds de garantie.` : "Les dotations sont à jour."),
    onError: (err) => toast.error(apiErrorMessage(err, "Dotation refusée.")),
  });
  const demanderAnnulation = (s: SinistreFonds) => {
    const motif = window.prompt(`Annuler la couverture de ${s.depense.numero} (${formatPrice(s.montant)}) : motif ?`);
    if (!motif) return;
    annuler.mutate({ id: s.id, motif }, {
      onSuccess: () => toast.success("Couverture annulée : le fonds retrouve la somme."),
      onError: (err) => toast.error(apiErrorMessage(err, "Annulation refusée.")),
    });
  };

  const colonnesDotations: Colonne<DotationFonds>[] = [
    { titre: "Mois", cellule: (d) => <strong className="capitalize whitespace-nowrap">{libelleMois(d.mois)}</strong>, masquerMobile: true },
    { titre: "Revenu net", cellule: (d) => <span className="tabular-nums whitespace-nowrap">{formatPrice(d.assiette)}</span>, className: "text-right" },
    { titre: "Taux", cellule: (d) => pourcent(d.taux), className: "text-right" },
    { titre: "Dotation due", cellule: (d) => <span className="tabular-nums whitespace-nowrap">{formatPrice(d.due)}</span>, className: "text-right" },
    { titre: "Écrite", cellule: (d) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(d.ecrite)}</strong>, className: "text-right" },
    { titre: "État", cellule: (d) => <Pill ton={etatDotation(d).ton}>{etatDotation(d).libelle}</Pill> },
  ];
  const colonnesSinistres: Colonne<SinistreFonds>[] = [
    { titre: "Dépense", cellule: (s) => (
      <span className="block min-w-0"><strong className="whitespace-nowrap">{s.depense.numero}</strong>
        <span className="block text-xs text-muted">{s.depense.libelle} · {formatPrice(s.depense.montant)}</span></span>
    ), masquerMobile: true },
    { titre: "Décision", cellule: (s) => (
      <span className="block min-w-0"><span className="block">{s.decision_reference}</span>
        <span className="block text-xs text-muted max-w-72">{s.motif}</span></span>
    ) },
    { titre: "Le", cellule: (s) => <span className="whitespace-nowrap">{formatDate(s.impute_le)}</span> },
    { titre: "Statut", cellule: (s) => (
      <span><Pill ton={s.statut === "impute" ? "vert" : "gris"}>{s.statut === "impute" ? "Couvert" : "Annulé"}</Pill>
        {s.motif_annulation && <span className="block text-xs text-muted mt-1 max-w-60">{s.motif_annulation}</span>}</span>
    ) },
    { titre: "Couvert", cellule: (s) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(s.montant)}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-5">
      <div className="grid sm:grid-cols-3 gap-3">
        <div className={cn("rounded-2xl p-4 border", data.sous_cible ? "bg-red-50 border-red-200" : "bg-surface border-gray-100")}>
          <p className="text-xs font-semibold text-muted">Solde du fonds</p>
          <p className="font-heading font-bold text-xl tabular-nums">{formatPrice(data.solde)}</p>
          {data.sous_cible && <p className="text-xs text-red-700 flex items-center gap-1 mt-1"><AlertTriangle size={12} aria-hidden /> Sous la cible de {formatPrice(data.cible)}</p>}
        </div>
        <div className="rounded-2xl p-4 bg-surface border border-gray-100">
          <p className="text-xs font-semibold text-muted">Cible</p>
          <p className="font-heading font-bold text-xl tabular-nums">{data.cible ? formatPrice(data.cible) : "Non fixée"}</p>
          <p className="text-xs text-muted">{data.cible ? "Alerte de l'équipe finance en dessous" : "À fixer par les associés : pas d'alerte tant qu'elle est à zéro"}</p>
        </div>
        <div className="rounded-2xl p-4 bg-surface border border-gray-100">
          <p className="text-xs font-semibold text-muted">Dotation</p>
          <p className="font-heading font-bold text-xl">{pourcent(data.taux)}</p>
          <p className="text-xs text-muted">du revenu net de chaque mois terminé, écrite chaque nuit et à la clôture</p>
        </div>
      </div>

      <Poches poches={data.poches} />

      <section className="space-y-3" aria-label="Dotations mensuelles">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-heading font-bold text-dark">Dotations mensuelles</h2>
          {data.peut_operer && (
            <button onClick={calculer} disabled={doter.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold disabled:opacity-60">
              <Calculator size={16} aria-hidden /> {aEcrire.length ? `Écrire les dotations (${aEcrire.length} mois)` : "Vérifier les dotations"}
            </button>
          )}
        </div>
        <AdminTable colonnes={colonnesDotations} lignes={data.dotations} cle={(d) => d.mois}
          titreMobile={(d) => <span className="flex justify-between gap-2 capitalize">{libelleMois(d.mois)}<span className="tabular-nums">{formatPrice(d.ecrite)}</span></span>} />
        {data.dotations.length === 0 && <p className="text-sm text-muted">Aucun mois au grand livre pour l&apos;instant.</p>}
      </section>

      <section className="space-y-3" aria-label="Sinistres couverts">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-heading font-bold text-dark">Sinistres couverts par le fonds</h2>
          {data.peut_operer && !couvrir && (
            <button onClick={() => setCouvrir(true)} disabled={!data.depenses_a_couvrir.length}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
              <ShieldCheck size={16} aria-hidden /> Couvrir un sinistre
            </button>
          )}
        </div>
        {couvrir && <FormSinistre fonds={data} onFermer={() => setCouvrir(false)} />}
        <AdminTable colonnes={colonnesSinistres} lignes={data.sinistres} cle={(s) => s.id}
          titreMobile={(s) => <span className="flex justify-between gap-2">{s.depense.numero}<span className="tabular-nums">{formatPrice(s.montant)}</span></span>}
          actions={(s) => data.peut_operer && s.statut === "impute"
            ? <ActionButton danger onClick={() => demanderAnnulation(s)} disabled={annuler.isPending}>Annuler</ActionButton> : null} />
        {data.sinistres.length === 0 && <p className="text-sm text-muted">Aucun sinistre couvert.</p>}
        <p className="text-xs text-muted">
          Un sinistre est d&apos;abord saisi comme une dépense D04 (« Litige pris en charge par la Garantie Kwa-Ba ») avec sa facture,
          dans Finance → Dépenses. Le fonds le couvre ensuite, au plus de son solde, avec la référence de la décision qui accorde la garantie.
        </p>
      </section>

      <p className="text-xs text-muted">
        Le fonds est une réserve, hors résultat : la dotation est une affectation (1301 / 118) et ne change pas le résultat du mois.
        Quand il couvre un sinistre, la réserve est reprise (118 / 1301) ; seul le sinistre payé est une charge (658). Comptes à
        confirmer par l&apos;expert-comptable (ADR-031).
      </p>
    </div>
  );
}

function Poches({ poches }: { poches: Fonds["poches"] }) {
  const lignes: [string, number][] = [
    ["Dû aux partenaires", poches.du_partenaires],
    ["Dû aux voyageurs", poches.du_voyageurs],
    ["Cautions détenues", poches.cautions_detenues],
    ["Fonds de garantie", poches.fonds_garantie],
  ];
  return (
    <section className="rounded-2xl p-4 bg-surface border border-gray-100" aria-label="Poches de la trésorerie">
      <h2 className="font-heading font-bold text-dark mb-2">Trésorerie et ses poches</h2>
      <dl className="text-sm divide-y divide-gray-50">
        <div className="flex justify-between gap-3 py-1.5"><dt>Argent détenu (comptes d&apos;argent)</dt><dd className="tabular-nums font-semibold">{formatPrice(poches.tresorerie)}</dd></div>
        {lignes.map(([libelle, montant]) => (
          <div key={libelle} className="flex justify-between gap-3 py-1.5 text-muted"><dt>− {libelle}</dt><dd className="tabular-nums">{formatPrice(montant)}</dd></div>
        ))}
        <div className="flex justify-between gap-3 pt-2"><dt className="font-semibold">= Trésorerie libre</dt>
          <dd className={cn("tabular-nums font-heading font-bold", poches.libre < 0 && "text-red-700")}>{formatPrice(poches.libre)}</dd></div>
      </dl>
    </section>
  );
}

function FormSinistre({ fonds, onFermer }: { fonds: Fonds; onFermer: () => void }) {
  const imputer = useImputerSinistre();
  const premiere = fonds.depenses_a_couvrir[0];
  const [s, setS] = useState({ depense: premiere?.id ?? "", montant: String(Math.min(premiere?.montant ?? 0, fonds.solde)),
    decision_reference: "", motif: "" });
  const depense = fonds.depenses_a_couvrir.find((d) => d.id === s.depense);
  const plafond = Math.min(depense?.montant ?? 0, fonds.solde);

  const envoyer = (e: React.FormEvent) => {
    e.preventDefault();
    imputer.mutate({ ...s, montant: Number(s.montant) }, {
      onSuccess: (r) => { toast.success(`${r.depense.numero} couverte par le fonds de garantie.`); onFermer(); },
      onError: (err) => toast.error(apiErrorMessage(err, "Couverture refusée.")),
    });
  };

  return (
    <form onSubmit={envoyer} className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label="Couvrir un sinistre">
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-sm min-w-0 sm:col-span-2"><span className="block text-xs font-semibold text-muted mb-1">Dépense du sinistre (D04, au grand livre)</span>
          <select required className={cn(CHAMP, "w-full")} value={s.depense}
            onChange={(e) => {
              const d = fonds.depenses_a_couvrir.find((x) => x.id === e.target.value);
              setS({ ...s, depense: e.target.value, montant: String(Math.min(d?.montant ?? 0, fonds.solde)) });
            }}>
            {fonds.depenses_a_couvrir.map((d) => <option key={d.id} value={d.id}>{d.numero} · {d.libelle} · {formatPrice(d.montant)}</option>)}
          </select></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Montant couvert (F CFA, au plus {formatPrice(plafond)})</span>
          <input type="number" required min={1} max={plafond} step={1} inputMode="numeric" className={cn(CHAMP, "w-full")}
            value={s.montant} onChange={(e) => setS({ ...s, montant: e.target.value })} /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Référence de la décision</span>
          <input required minLength={3} maxLength={120} className={cn(CHAMP, "w-full")} value={s.decision_reference}
            onChange={(e) => setS({ ...s, decision_reference: e.target.value })} placeholder="Ex. : DEC-2026-007" /></label>
        <label className="text-sm min-w-0 sm:col-span-2"><span className="block text-xs font-semibold text-muted mb-1">Le sinistre</span>
          <textarea required minLength={10} maxLength={1000} rows={2} className={cn(CHAMP, "w-full")} value={s.motif}
            onChange={(e) => setS({ ...s, motif: e.target.value })} placeholder="Ce qui s'est passé, et pourquoi la garantie s'applique" /></label>
      </div>
      {fonds.solde <= 0 && <p className="text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">Le fonds est vide : il ne peut rien couvrir pour l&apos;instant.</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={imputer.isPending || plafond <= 0} className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
          {imputer.isPending ? "Envoi…" : "Couvrir par le fonds"}
        </button>
        <button type="button" onClick={onFermer} className="px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Annuler</button>
      </div>
    </form>
  );
}
