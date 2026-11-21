"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, FileText, Paperclip } from "lucide-react";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { messageErreurPdf, telechargerPdf } from "@/lib/documents";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import { urlDocumentCaution, urlJustificatif, type CautionFinance, type StatutCaution } from "../api";
import { useCautions, useJustificatifs } from "../hooks";
import { ErreurLecture } from "./communs";

const STATUTS: Record<StatutCaution, { libelle: string; ton: "bleu" | "vert" | "orange" }> = {
  detenue: { libelle: "Détenue", ton: "bleu" },
  restituee: { libelle: "Restituée", ton: "vert" },
  retenue: { libelle: "Retenue", ton: "orange" },
};
const FILTRES: [string, string][] = [["detenue", "Détenues"], ["retard", "En retard"], ["", "Toutes"], ["restituee", "Restituées"], ["retenue", "Avec retenue"]];

async function telecharger(url: string, nom: string) {
  try {
    await telechargerPdf(url, nom);
  } catch (err) {
    toast.error(await messageErreurPdf(err, "Téléchargement impossible."));
  }
}

/**
 * Register of the deposits (GL-13): every deposit held for a traveller, its return date, and its settlement with its
 * document (GL-14): a REC receipt when it is given back in full, a RET notice with the motivated decision and its
 * evidence when part of it is kept. The deposits held are the traveller's money, never Kwa-Ba's.
 */
export default function Cautions() {
  const [filtre, setFiltre] = useState("detenue");
  const { data, isLoading, isError, error } = useCautions(filtre === "retard" ? "" : filtre, filtre === "retard");
  const [pieces, setPieces] = useState<CautionFinance | null>(null);

  const colonnes: Colonne<CautionFinance>[] = [
    { titre: "Réservation", cellule: (c) => <strong className="whitespace-nowrap">{c.reference}</strong>, masquerMobile: true },
    { titre: "Voyageur", cellule: (c) => c.voyageur || "—" },
    { titre: "Reçue le", cellule: (c) => formatDate(c.recue_le) },
    { titre: "À rendre avant", cellule: (c) => <span className={cn("whitespace-nowrap", c.en_retard && "text-red-700 font-semibold")}>{formatDate(c.date_limite)}{c.en_retard && " · en retard"}</span> },
    { titre: "Statut", cellule: (c) => (
      <span><Pill ton={STATUTS[c.statut].ton}>{STATUTS[c.statut].libelle}</Pill>
        {c.montant_retenu > 0 && <span className="block text-xs text-muted mt-1 max-w-64">Retenue {formatPrice(c.montant_retenu)} : {c.motif_retenue} (CGV art. {c.cgv_article})</span>}
      </span>
    ) },
    { titre: "Caution", cellule: (c) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(c.montant)}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-4">
      {data && (
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="rounded-2xl p-4 bg-surface border border-gray-100">
            <p className="text-xs font-semibold text-muted">Cautions détenues</p>
            <p className="font-heading font-bold text-xl tabular-nums">{formatPrice(data.total_detenu)}</p>
            <p className="text-xs text-muted">Argent des voyageurs, à rendre : jamais un revenu de Kwa-Ba</p>
          </div>
          <div className={cn("rounded-2xl p-4 border", data.en_retard ? "bg-red-50 border-red-200" : "bg-surface border-gray-100")}>
            <p className="text-xs font-semibold text-muted">À rendre, date dépassée</p>
            <p className="font-heading font-bold text-xl tabular-nums flex items-center gap-2">
              {data.en_retard > 0 && <AlertTriangle size={18} className="text-red-700" aria-hidden />}{data.en_retard}
            </p>
            <p className="text-xs text-muted">À régulariser : restitution ou document manquant</p>
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {FILTRES.map(([code, libelle]) => (
          <button key={code} onClick={() => setFiltre(code)} aria-pressed={filtre === code}
            className={cn("px-3 py-1.5 rounded-lg text-sm font-semibold border", filtre === code ? "border-primary text-brand bg-primary/5" : "border-gray-200 text-dark hover:bg-gray-50")}>
            {libelle}
          </button>
        ))}
      </div>
      {isError && <ErreurLecture erreur={error} />}
      <AdminTable colonnes={colonnes} lignes={data?.cautions} cle={(c) => `${c.objet_type}-${c.objet_id}`} chargement={isLoading}
        titreMobile={(c) => <span className="flex justify-between gap-2">{c.reference}<span className="tabular-nums">{formatPrice(c.montant)}</span></span>}
        actions={(c) => (
          <>
            {c.document_numero && (
              <ActionButton onClick={() => telecharger(urlDocumentCaution(c.document_numero), `${c.document_numero}.pdf`)}>
                <FileText size={12} className="inline" aria-hidden /> {c.document_numero}
              </ActionButton>
            )}
            {c.montant_retenu > 0 && <ActionButton onClick={() => setPieces(c)}><Paperclip size={12} className="inline" aria-hidden /> Pièces</ActionButton>}
          </>
        )} />
      {pieces && <Pieces caution={pieces} onFermer={() => setPieces(null)} />}
      <p className="text-xs text-muted">
        Aujourd&apos;hui, seule la location de voiture sans chauffeur garde une caution en ligne. La caution des séjours rejoindra ce registre quand elle existera.
      </p>
    </div>
  );
}

function Pieces({ caution, onFermer }: { caution: CautionFinance; onFermer: () => void }) {
  const { data, isLoading } = useJustificatifs(caution.objet_type, caution.objet_id);
  return (
    <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-2" aria-label="Pièces justificatives">
      <div className="flex justify-between gap-2">
        <h2 className="font-heading font-bold text-dark">Pièces justificatives · {caution.reference}</h2>
        <button onClick={onFermer} className="text-sm font-semibold text-brand">Fermer</button>
      </div>
      {isLoading && <div className="h-12 skeleton rounded-xl" />}
      {data?.length === 0 && <p className="text-sm text-muted">Aucune pièce.</p>}
      <ul className="text-sm divide-y divide-gray-50">
        {data?.map((j) => (
          <li key={j.id} className="flex justify-between gap-2 py-2">
            <span>{j.nom} <span className="text-muted">· {Math.ceil(j.taille / 1024)} Ko · {formatDate(j.ajoute_le)}</span></span>
            <ActionButton onClick={() => telecharger(urlJustificatif(j.id), j.nom)}>Ouvrir</ActionButton>
          </li>
        ))}
      </ul>
    </section>
  );
}
