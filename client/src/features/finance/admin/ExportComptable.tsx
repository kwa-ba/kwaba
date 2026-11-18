"use client";

import { useState } from "react";
import Link from "next/link";
import { FileSpreadsheet } from "lucide-react";
import { isoDate } from "@/lib/utils";
import { urlExportEcritures } from "../api";
import { BoutonTelecharger, Periode, moisEnCours } from "./communs";

/** Shortcuts of the periods an accountant asks for. */
function raccourcis(): { libelle: string; debut: string; fin: string }[] {
  const a = new Date();
  const moisPrecedent = new Date(a.getFullYear(), a.getMonth() - 1, 1);
  return [
    { libelle: "Ce mois-ci", ...moisEnCours() },
    { libelle: "Mois dernier", debut: isoDate(moisPrecedent), fin: isoDate(new Date(a.getFullYear(), a.getMonth(), 0)) },
    { libelle: "Depuis le 1er janvier", debut: isoDate(new Date(a.getFullYear(), 0, 1)), fin: isoDate(a) },
    { libelle: "Année dernière", debut: isoDate(new Date(a.getFullYear() - 1, 0, 1)), fin: isoDate(new Date(a.getFullYear() - 1, 11, 31)) },
  ];
}

/**
 * The file for the accounting firm (GL-6): every accounting entry of a period, two lines per movement, with journal,
 * account, sub-account, document, debit and credit, ready to import without typing anything again. Every export is
 * logged in the activity log.
 */
export default function ExportComptable() {
  const [{ debut, fin }, setPeriode] = useState(moisEnCours);

  return (
    <div className="space-y-5 max-w-3xl">
      <section className="bg-surface rounded-2xl border border-gray-100 p-5 space-y-4">
        <div className="flex items-start gap-3">
          <FileSpreadsheet size={22} className="text-brand shrink-0 mt-0.5" aria-hidden />
          <div>
            <h2 className="font-heading font-bold text-dark">Écritures comptables</h2>
            <p className="text-sm text-muted mt-1">
              Fichier CSV (séparateur « ; », UTF-8) : journal, date, pièce, compte, compte auxiliaire, libellé, débit, crédit, devise,
              numéro de mouvement. Une période d&apos;un an au plus.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {raccourcis().map((r) => (
            <button key={r.libelle} onClick={() => setPeriode({ debut: r.debut, fin: r.fin })}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${r.debut === debut && r.fin === fin ? "border-primary text-brand bg-primary/5" : "border-gray-200 text-dark hover:bg-gray-50"}`}>
              {r.libelle}
            </button>
          ))}
        </div>
        <Periode debut={debut} fin={fin} onChange={(d, f) => setPeriode({ debut: d, fin: f })}>
          <div className="sm:ml-auto"><BoutonTelecharger url={urlExportEcritures(debut, fin)} nom="kwaba-ecritures.csv" libelle="Télécharger les écritures" principal disabled={!debut || !fin || debut > fin} /></div>
        </Periode>
      </section>

      <p className="text-sm text-muted">
        Encaissements, remboursements et versements de la période (CSV et PDF) : page{" "}
        <Link href="/backoffice/finances/encaissements" className="text-brand font-semibold hover:underline">Encaissements</Link>.
        Numéros de comptes SYSCOHADA à valider par l&apos;expert-comptable avant le paramétrage définitif.
      </p>
    </div>
  );
}
