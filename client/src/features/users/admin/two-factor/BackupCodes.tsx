"use client";

import { AlertTriangle, Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { backupCodesText } from "./rules";

const bouton = "inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl border border-gray-200 bg-surface text-sm font-bold text-dark hover:bg-gray-50";

/** The 10 backup codes, shown only once, with copy and download. */
export default function BackupCodes({ codes, account, noted, onNoted }: {
  codes: string[]; account: string; noted: boolean; onNoted: (noted: boolean) => void;
}) {
  const texte = () => backupCodesText(codes, account, new Date());

  const copier = async () => {
    try {
      await navigator.clipboard.writeText(texte());
      toast.success("Codes copiés");
    } catch {
      toast.error("Copie impossible : téléchargez les codes.");
    }
  };

  const telecharger = () => {
    const url = URL.createObjectURL(new Blob([texte()], { type: "text/plain;charset=utf-8" }));
    const lien = Object.assign(document.createElement("a"), { href: url, download: "kwa-ba-codes-de-secours.txt" });
    lien.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <ol className="grid grid-cols-2 gap-2">
        {codes.map((code, i) => (
          <li key={code} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-gray-50 border border-gray-100">
            <span className="text-[11px] text-muted tabular-nums">{String(i + 1).padStart(2, "0")}</span>
            <code className="font-mono text-sm font-bold text-dark">{code}</code>
          </li>
        ))}
      </ol>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={copier} className={bouton}><Copy size={16} aria-hidden /> Copier les codes</button>
        <button type="button" onClick={telecharger} className={bouton}><Download size={16} aria-hidden /> Télécharger</button>
      </div>
      <p className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
        <AlertTriangle size={16} aria-hidden className="shrink-0 mt-0.5" />
        Ces codes ne seront plus affichés après cette page. Rangez-les hors ligne ou dans un gestionnaire de mots de passe.
      </p>
      <label className="flex items-center gap-3 text-sm font-bold text-dark cursor-pointer">
        <input type="checkbox" checked={noted} onChange={(e) => onNoted(e.target.checked)}
          className="w-5 h-5 rounded border-gray-300 accent-primary" />
        J&apos;ai noté mes codes
      </label>
    </div>
  );
}
