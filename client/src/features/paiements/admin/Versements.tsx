"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, RotateCcw } from "lucide-react";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import {
  lireVersementsPartenaires, relancerRecuperation, relancerVersement,
  type RecuperationHote, type StatutVersementPartenaire, type VersementPartenaire,
} from "../api";

// One cache key per read (documentation/frontieres-front.md)
const CLES = { tout: ["admin", "paiements", "versements"] as const, liste: (statut: string) => ["admin", "paiements", "versements", statut] as const };
const STATUTS: Record<StatutVersementPartenaire, { libelle: string; ton: "bleu" | "vert" | "rouge" | "gris" | "orange" }> = {
  planifie: { libelle: "Planifié", ton: "bleu" },
  en_cours: { libelle: "En cours", ton: "orange" },
  envoye: { libelle: "Envoyé", ton: "vert" },
  echoue: { libelle: "Échoué", ton: "rouge" },
  annule: { libelle: "Annulé", ton: "gris" },
};
const FILTRES: [string, string][] = [["", "À verser"], ["echoue", "En échec"], ["planifie", "Planifiés"], ["en_cours", "En cours"], ["envoye", "Envoyés"]];

/**
 * Payouts to the partners (GL-11): what is owed to each host, driver and vehicle owner, its due date and state, the
 * late and failed ones (sent again from here), and the recoveries of payouts made for stays cancelled afterwards
 * (GL-23): withheld on the host's next payouts, or asked back when none is coming.
 */
export default function Versements() {
  const [statut, setStatut] = useState("");
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({ queryKey: CLES.liste(statut), queryFn: () => lireVersementsPartenaires(statut) });
  const relancer = useMutation({ mutationFn: (v: VersementPartenaire) => relancerVersement(v.type, v.id),
    onSuccess: (r) => { toast.success(r.detail); qc.invalidateQueries({ queryKey: CLES.tout }); },
    onError: (err) => toast.error(apiErrorMessage(err, "Relance refusée.")) });
  const demander = useMutation({ mutationFn: (r: RecuperationHote) => relancerRecuperation(r.id),
    onSuccess: (r) => { toast.success(r.detail); qc.invalidateQueries({ queryKey: CLES.tout }); },
    onError: (err) => toast.error(apiErrorMessage(err, "Envoi refusé.")) });

  const colonnes: Colonne<VersementPartenaire>[] = [
    { titre: "Bénéficiaire", cellule: (v) => (
      <span className="block min-w-0"><strong>{v.beneficiaire || "—"}</strong>
        <span className="block text-xs text-muted">{v.categorie} · {v.objet}</span></span>
    ), masquerMobile: true },
    { titre: "Prévu le", cellule: (v) => (
      <span className={cn("whitespace-nowrap", v.en_retard && "text-red-700 font-semibold")}>{formatDate(v.date_prevue)}{v.en_retard && " · en retard"}</span>
    ) },
    { titre: "Statut", cellule: (v) => (
      <span><Pill ton={STATUTS[v.statut].ton}>{STATUTS[v.statut].libelle}</Pill>
        {v.tentatives > 0 && <span className="block text-xs text-muted mt-1">{v.tentatives} essai{v.tentatives > 1 ? "s" : ""}</span>}
        {v.derniere_erreur && <span className="block text-xs text-muted mt-1 max-w-64">{v.derniere_erreur}</span>}</span>
    ) },
    { titre: "Montant", cellule: (v) => (
      <span className="block text-right"><strong className="tabular-nums whitespace-nowrap">{formatPrice(v.montant)}</strong>
        {v.retenue > 0 && <span className="block text-xs text-muted whitespace-nowrap">dont {formatPrice(v.retenue)} retenus</span>}</span>
    ), className: "text-right" },
  ];
  const colonnesRecup: Colonne<RecuperationHote>[] = [
    { titre: "Hôte", cellule: (r) => <span className="block"><strong>{r.hote || "—"}</strong><span className="block text-xs text-muted">{r.objet} · {r.motif}</span></span>, masquerMobile: true },
    { titre: "Depuis", cellule: (r) => <span className="whitespace-nowrap">{formatDate(r.cree_le)}</span> },
    { titre: "Suite", cellule: (r) => r.statut !== "en_cours" ? <Pill ton="gris">{r.statut === "soldee" ? "Récupéré" : "Sans objet"}</Pill>
      : r.versement_a_venir ? <span className="text-xs">Retenu sur son prochain versement</span>
        : <span className="text-xs text-amber-800">Aucun versement à venir : à demander{r.relances > 0 && ` (${r.relances} demande${r.relances > 1 ? "s" : ""}, la dernière le ${formatDate(r.derniere_relance_le as string)})`}</span> },
    { titre: "Reste", cellule: (r) => <span className="block text-right"><strong className="tabular-nums whitespace-nowrap">{formatPrice(r.reste)}</strong>
      <span className="block text-xs text-muted whitespace-nowrap">sur {formatPrice(r.montant)}</span></span>, className: "text-right" },
  ];

  return (
    <div className="space-y-5">
      {data && (
        <div className="grid sm:grid-cols-4 gap-3">
          <Carte titre="Dû aux partenaires" valeur={formatPrice(data.totaux.du)} />
          <Carte titre="En retard" valeur={String(data.totaux.en_retard)} alerte={data.totaux.en_retard > 0}
            note={`plus de ${data.retard_heures} h après la date prévue`} />
          <Carte titre="En échec" valeur={String(data.totaux.echoues)} alerte={data.totaux.echoues > 0} note="à relancer" />
          <Carte titre="À récupérer auprès d'hôtes" valeur={formatPrice(data.totaux.a_recuperer)} alerte={data.totaux.a_recuperer > 0} />
        </div>
      )}
      <div className="flex flex-wrap gap-2" role="tablist">
        {FILTRES.map(([code, libelle]) => (
          <button key={code} role="tab" aria-selected={statut === code} onClick={() => setStatut(code)}
            className={cn("px-3 py-1.5 rounded-lg text-sm font-semibold border",
              statut === code ? "border-primary text-brand bg-primary/5" : "border-gray-200 text-dark hover:bg-gray-50")}>
            {libelle}
          </button>
        ))}
      </div>
      {isError && <p role="alert" className="text-sm text-red-700">{apiErrorMessage(error, "Impossible de lire les versements.")}</p>}
      {data && !data.peut_operer && (
        <p className="text-sm bg-amber-50 text-amber-900 rounded-xl px-4 py-3">Consultation seulement : relancer un versement demande la permission « Opérations financières ».</p>
      )}
      <AdminTable colonnes={colonnes} lignes={data?.versements} cle={(v) => `${v.type}:${v.id}`} chargement={isLoading}
        titreMobile={(v) => <span className="flex justify-between gap-2">{v.beneficiaire || v.objet}<span className="tabular-nums">{formatPrice(v.montant)}</span></span>}
        actions={(v) => data?.peut_operer && v.relancable
          ? <ActionButton onClick={() => relancer.mutate(v)} disabled={relancer.isPending}><RotateCcw size={12} className="inline" aria-hidden /> Relancer</ActionButton> : null} />
      {data?.versements.length === 0 && <p className="text-sm text-muted">Aucun versement pour ce filtre.</p>}

      <section className="space-y-3" aria-label="Récupérations auprès des hôtes">
        <h2 className="font-heading font-bold text-dark flex items-center gap-2"><AlertTriangle size={16} aria-hidden /> Séjours annulés après le versement</h2>
        <AdminTable colonnes={colonnesRecup} lignes={data?.recuperations} cle={(r) => r.id}
          titreMobile={(r) => <span className="flex justify-between gap-2">{r.hote}<span className="tabular-nums">{formatPrice(r.reste)}</span></span>}
          actions={(r) => data?.peut_operer && r.statut === "en_cours" && !r.versement_a_venir
            ? <ActionButton onClick={() => demander.mutate(r)} disabled={demander.isPending}>Demander le remboursement</ActionButton> : null} />
        {data?.recuperations.length === 0 && <p className="text-sm text-muted">Aucun séjour annulé après son versement.</p>}
        <p className="text-xs text-muted">
          Quand un séjour est annulé et remboursé après le versement à l&apos;hôte, ce qu&apos;il a reçu au-delà de ce que le barème lui laisse
          est retenu sur ses prochains versements. S&apos;il n&apos;en a pas, la demande de remboursement part d&apos;ici, et la somme reste affichée tant qu&apos;elle n&apos;est pas récupérée.
        </p>
      </section>
    </div>
  );
}

function Carte({ titre, valeur, note, alerte }: { titre: string; valeur: string; note?: string; alerte?: boolean }) {
  return (
    <div className={cn("rounded-2xl p-4 border", alerte ? "bg-red-50 border-red-200" : "bg-surface border-gray-100")}>
      <p className="text-xs font-semibold text-muted">{titre}</p>
      <p className="font-heading font-bold text-xl tabular-nums">{valeur}</p>
      {note && <p className="text-xs text-muted">{note}</p>}
    </div>
  );
}
