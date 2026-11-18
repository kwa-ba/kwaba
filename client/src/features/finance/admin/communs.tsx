"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { apiErrorMessage } from "@/lib/api";
import { messageErreurPdf, telechargerPdf } from "@/lib/documents";
import { cn, formatPrice, isoDate } from "@/lib/utils";

export const CHAMP = "px-3 py-2 border border-gray-200 rounded-xl bg-surface text-base sm:text-sm focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary";

/** First day of this month and today, as YYYY-MM-DD. */
export function moisEnCours(): { debut: string; fin: string } {
  const aujourdhui = new Date();
  return { debut: isoDate(new Date(aujourdhui.getFullYear(), aujourdhui.getMonth(), 1)), fin: isoDate(aujourdhui) };
}

/** « 2026-10-01 » → « octobre 2026 » */
export function libelleMois(mois: string): string {
  const [annee, m] = mois.split("-").map(Number);
  return new Date(annee, m - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

/** Period of a book: from, to (both included), one year at most (the server refuses more). */
export function Periode({ debut, fin, onChange, children }: {
  debut: string; fin: string; onChange: (debut: string, fin: string) => void; children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-3">
      <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Du</span>
        <input type="date" className={CHAMP} value={debut} max={fin} onChange={(e) => onChange(e.target.value, fin)} /></label>
      <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Au</span>
        <input type="date" className={CHAMP} value={fin} min={debut} onChange={(e) => onChange(debut, e.target.value)} /></label>
      {children}
    </div>
  );
}

/** A select of codes with an « all » choice. */
export function ChoixCode({ libelle, valeur, onChange, options, tous = "Tous" }: {
  libelle: string; valeur: string; onChange: (v: string) => void; options: { code: string; libelle: string }[]; tous?: string;
}) {
  return (
    <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">{libelle}</span>
      <select className={cn(CHAMP, "w-full")} value={valeur} onChange={(e) => onChange(e.target.value)}>
        <option value="">{tous}</option>
        {options.map((o) => <option key={o.code} value={o.code}>{o.code} · {o.libelle}</option>)}
      </select>
    </label>
  );
}

/** A debit or credit cell: empty at zero, as accountants read it. */
export function Somme({ montant, className }: { montant: number; className?: string }) {
  return <span className={cn("tabular-nums whitespace-nowrap", className)}>{montant ? formatPrice(montant) : ""}</span>;
}

/** A balance with its side: « 12 000 F D » (debit) or « 12 000 F C » (credit). */
export function Solde({ solde, className }: { solde: number; className?: string }) {
  if (!solde) return <span className={cn("tabular-nums text-muted", className)}>0</span>;
  return (
    <span className={cn("tabular-nums whitespace-nowrap font-semibold", className)}>
      {formatPrice(Math.abs(solde))} <abbr title={solde > 0 ? "Débiteur" : "Créditeur"} className="no-underline text-muted text-xs">{solde > 0 ? "D" : "C"}</abbr>
    </span>
  );
}

/** Downloads a file of the API (CSV export); the server logs every export. */
export function BoutonTelecharger({ url, nom, libelle, principal, disabled }: {
  url: string; nom: string; libelle: string; principal?: boolean; disabled?: boolean;
}) {
  const [enCours, setEnCours] = useState(false);
  const telecharger = async () => {
    setEnCours(true);
    try {
      await telechargerPdf(url, nom);
    } catch (err) {
      toast.error(await messageErreurPdf(err, "Export impossible."));
    } finally {
      setEnCours(false);
    }
  };
  return (
    <button onClick={telecharger} disabled={enCours || disabled}
      className={cn("flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold disabled:opacity-50",
        principal ? "bg-primary text-white font-bold" : "border border-gray-200 bg-surface")}>
      <Download size={16} aria-hidden /> {enCours ? "Export…" : libelle}
    </button>
  );
}

/** Error of a read, with its message from the server when there is one. */
export function ErreurLecture({ erreur }: { erreur: unknown }) {
  return <p role="alert" className="text-sm text-red-700">{apiErrorMessage(erreur, "Impossible de lire le grand livre.")}</p>;
}
