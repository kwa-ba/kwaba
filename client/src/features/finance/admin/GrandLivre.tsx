"use client";

import { useState } from "react";
import { X } from "lucide-react";
import AdminTable, { Pagination, SearchInput, type Colonne } from "@/components/backoffice/AdminTable";
import { formatDate, formatPrice } from "@/lib/utils";
import type { FiltresMouvements, LigneMouvement } from "../api";
import { useMouvements, useReferentielsFinance } from "../hooks";
import { CHAMP, ChoixCode } from "./communs";
import { FAMILLES, OFFRES, TIERS } from "./libelles";

function Montant({ m }: { m: LigneMouvement }) {
  return (
    <span className={`tabular-nums font-semibold whitespace-nowrap ${m.montant_signe < 0 ? "text-red-700" : "text-emerald-700"}`}>
      {m.montant_signe < 0 ? "−" : "+"} {formatPrice(m.montant)}
    </span>
  );
}

function Nature({ m }: { m: LigneMouvement }) {
  return (
    <span>
      <span className={`inline-block rounded-md px-1.5 py-0.5 text-xs font-bold mr-1.5 ${FAMILLES[m.famille] ?? "bg-gray-100 text-dark"}`}>{m.nature_code}</span>
      {m.nature_libelle}
      {m.annule_mouvement_id && <span className="block text-xs text-muted">Corrige la ligne {m.annule_mouvement_id}{m.motif ? ` : ${m.motif}` : ""}</span>}
    </span>
  );
}

const tiers = (m: LigneMouvement) => (m.tiers_type
  ? <>{m.nom || m.tiers_id || "À désigner"} <span className="text-muted">· {TIERS[m.tiers_type] ?? m.tiers_type}</span></>
  : <span className="text-muted">Kwa-Ba</span>);

const COLONNES: Colonne<LigneMouvement>[] = [
  { titre: "N°", cellule: (m) => <span className="text-muted tabular-nums">{m.id}</span>, masquerMobile: true },
  { titre: "Date", cellule: (m) => <span className="whitespace-nowrap">{formatDate(m.date_evenement)}</span> },
  { titre: "Nature", cellule: (m) => <Nature m={m} />, masquerMobile: true },
  { titre: "Offre", cellule: (m) => OFFRES[m.offre_code] ?? m.offre_code },
  { titre: "Tiers", cellule: tiers },
  { titre: "Compte", cellule: (m) => m.compte_argent_code },
  { titre: "Pièce", cellule: (m) => <span className="text-muted whitespace-nowrap">{m.piece_reference ?? "—"}</span> },
  { titre: "Montant", cellule: (m) => <Montant m={m} />, className: "text-right" },
];

const VIDE: FiltresMouvements = {};

/**
 * Every line of the ledger, newest first, with filters that combine (GL-2): period, nature, family, offer, third
 * party, money account, document and direction. A written line never changes: an error is corrected by an inverse
 * line, and both stay visible.
 */
export default function GrandLivre() {
  const [filtres, setFiltres] = useState<FiltresMouvements>(VIDE);
  const [page, setPage] = useState(1);
  const { data, isLoading, isFetching, isError, refetch } = useMouvements(filtres, page);
  const { data: ref } = useReferentielsFinance();

  const changer = (champ: keyof FiltresMouvements, valeur: string) => {
    setFiltres((f) => ({ ...f, [champ]: valeur || undefined }));
    setPage(1);
  };
  const actifs = Object.values(filtres).filter(Boolean).length;
  const natures = (ref?.natures ?? []).filter((n) => !filtres.famille || n.famille === filtres.famille);

  return (
    <div className="space-y-4">
      <section className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-3" aria-label="Filtres">
        <div className="flex flex-col sm:flex-row gap-3">
          <SearchInput value={filtres.piece ?? ""} onChange={(v) => changer("piece", v)} placeholder="Pièce : référence de réservation, facture…" />
          <label className="text-sm"><span className="sr-only">Du</span>
            <input type="date" aria-label="Du" className={CHAMP} value={filtres.du ?? ""} max={filtres.au} onChange={(e) => changer("du", e.target.value)} /></label>
          <label className="text-sm"><span className="sr-only">Au</span>
            <input type="date" aria-label="Au" className={CHAMP} value={filtres.au ?? ""} min={filtres.du} onChange={(e) => changer("au", e.target.value)} /></label>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <ChoixCode libelle="Famille" valeur={filtres.famille ?? ""} onChange={(v) => { changer("famille", v); changer("nature", ""); }} options={ref?.familles ?? []} tous="Toutes" />
          <ChoixCode libelle="Nature" valeur={filtres.nature ?? ""} onChange={(v) => changer("nature", v)} options={natures} tous="Toutes" />
          <ChoixCode libelle="Offre" valeur={filtres.offre ?? ""} onChange={(v) => changer("offre", v)} options={ref?.offres ?? []} tous="Toutes" />
          <ChoixCode libelle="Type de tiers" valeur={filtres.tiers_type ?? ""} onChange={(v) => changer("tiers_type", v)} options={ref?.tiers_types ?? []} />
          <ChoixCode libelle="Compte d'argent" valeur={filtres.compte_argent ?? ""} onChange={(v) => changer("compte_argent", v)} options={ref?.comptes_argent ?? []} />
          <ChoixCode libelle="Sens" valeur={filtres.sens ?? ""} onChange={(v) => changer("sens", v)}
            options={[{ code: "entree", libelle: "Entrées" }, { code: "sortie", libelle: "Sorties" }]} />
        </div>
        {(actifs > 0 || filtres.tiers_id) && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {filtres.tiers_id && <span className="text-muted">Tiers n° {filtres.tiers_id}</span>}
            <button onClick={() => { setFiltres(VIDE); setPage(1); }} className="flex items-center gap-1 font-semibold text-brand hover:underline">
              <X size={14} aria-hidden /> Effacer les filtres ({actifs})
            </button>
          </div>
        )}
      </section>

      {data && <p className="text-sm text-muted">{data.count} ligne{data.count > 1 ? "s" : ""}</p>}
      <AdminTable colonnes={COLONNES} lignes={data?.results} cle={(m) => String(m.id)} chargement={isLoading || isFetching}
        erreur={isError} onReessayer={() => refetch()}
        titreMobile={(m) => <div className="flex items-start justify-between gap-3"><Nature m={m} /><Montant m={m} /></div>} />
      {data && <Pagination page={page} count={data.count} pageSize={data.page_size} onChange={setPage} />}
      <p className="text-xs text-muted">Une ligne écrite ne se modifie jamais : une erreur se corrige par une ligne inverse, et les deux restent visibles.</p>
    </div>
  );
}
