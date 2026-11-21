"use client";

import { RefreshCw } from "lucide-react";
import { formatDate } from "@/lib/utils";

/** When the ledger was read, and a button to read it again (pages of the Finance heading). */
export default function Actualiser({ lu, enCours, onActualiser }: { lu?: number; enCours: boolean; onActualiser: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {lu ? (
        <p className="text-sm text-muted">
          Lu le {formatDate(new Date(lu).toISOString())} à {new Date(lu).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
        </p>
      ) : null}
      <button onClick={onActualiser} disabled={enCours} className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 bg-surface text-sm font-semibold disabled:opacity-50 sm:ml-auto">
        <RefreshCw size={16} aria-hidden className={enCours ? "animate-spin" : ""} /> Actualiser
      </button>
    </div>
  );
}
