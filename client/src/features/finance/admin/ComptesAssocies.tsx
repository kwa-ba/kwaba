"use client";

import { useState } from "react";
import { toast } from "sonner";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import type { CompteCourantAssocie, LigneCompteCourant } from "../api";
import { useComptesCourants, useEnregistrerAssocie, useReleveAssocie } from "../hooks";
import { ErreurLecture } from "./communs";

/**
 * Associates' current accounts (GL-16): what Kwa-Ba owes each associate, read from the ledger (the expenses they
 * advanced, F03; their advances, F02; what was paid back to them, F04), with the share capital and each part. A
 * current account is never in debit: the ledger refuses any line that would make it so (articles of association,
 * art. 19). Repayments open with the bank account (decision of 2026-11-19).
 */
export default function ComptesAssocies() {
  const { data, isLoading, isError, error } = useComptesCourants();
  const enregistrer = useEnregistrerAssocie();
  const [releve, setReleve] = useState<CompteCourantAssocie | null>(null);

  const changerPart = (a: CompteCourantAssocie) => {
    const saisie = window.prompt(`Part du capital de ${a.nom} (F CFA) :`, String(a.capital_souscrit));
    if (saisie === null) return;
    const part = Number(saisie.replace(/\s/g, ""));
    if (!Number.isInteger(part) || part < 0) {
      toast.error("La part du capital est un nombre entier de francs CFA.");
      return;
    }
    enregistrer.mutate({ id: a.id, nom: a.nom, capital_souscrit: part }, {
      onSuccess: () => toast.success(`Part de ${a.nom} enregistrée.`),
      onError: (err) => toast.error(apiErrorMessage(err, "Part refusée.")),
    });
  };

  const colonnes: Colonne<CompteCourantAssocie>[] = [
    { titre: "Associé", cellule: (a) => (
      <span className={cn("block", !a.actif && "text-muted")}><strong>{a.nom}</strong>{!a.actif && " · inactif"}
        {a.email && <span className="block text-xs text-muted">{a.email}</span>}</span>
    ), masquerMobile: true },
    { titre: "Part du capital", cellule: (a) => <span className="tabular-nums whitespace-nowrap">{formatPrice(a.capital_souscrit)}</span>, className: "text-right" },
    { titre: "Avancé", cellule: (a) => <span className="tabular-nums whitespace-nowrap">{formatPrice(a.avances)}</span>, className: "text-right" },
    { titre: "Remboursé", cellule: (a) => <span className="tabular-nums whitespace-nowrap">{formatPrice(a.remboursements)}</span>, className: "text-right" },
    { titre: "Kwa-Ba lui doit", cellule: (a) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(a.solde)}</strong>, className: "text-right" },
  ];

  const ecart = data ? data.capital_social - data.capital_souscrit : 0;
  return (
    <div className="space-y-4">
      {isError && <ErreurLecture erreur={error} />}
      {data && (
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="rounded-2xl p-4 bg-surface border border-gray-100">
            <p className="text-xs font-semibold text-muted">Kwa-Ba doit aux associés</p>
            <p className="font-heading font-bold text-xl tabular-nums">{formatPrice(data.totaux.solde)}</p>
            <p className="text-xs text-muted">Compte courant 462 : avancé {formatPrice(data.totaux.avances)}, remboursé {formatPrice(data.totaux.remboursements)}</p>
          </div>
          <div className="rounded-2xl p-4 bg-surface border border-gray-100">
            <p className="text-xs font-semibold text-muted">Capital social</p>
            <p className="font-heading font-bold text-xl tabular-nums">{formatPrice(data.capital_social)}</p>
            <p className={cn("text-xs", ecart ? "text-amber-800" : "text-muted")}>
              {ecart ? `Parts réparties : ${formatPrice(data.capital_souscrit)}, reste ${formatPrice(ecart)} à attribuer` : "Entièrement réparti entre les associés"}
            </p>
          </div>
          <div className="rounded-2xl p-4 bg-surface border border-gray-100">
            <p className="text-xs font-semibold text-muted">Remboursements</p>
            <p className="text-sm text-dark mt-1">{data.remboursements_ouverts ? "Ouverts." : "Pas encore ouverts : ils viendront avec le compte bancaire. Les sommes dues restent au compte courant."}</p>
          </div>
        </div>
      )}

      <AdminTable colonnes={colonnes} lignes={data?.associes} cle={(a) => a.id} chargement={isLoading}
        titreMobile={(a) => <span className="flex justify-between gap-2">{a.nom}<span className="tabular-nums">{formatPrice(a.solde)}</span></span>}
        actions={(a) => (
          <>
            <ActionButton onClick={() => setReleve(a)}>Relevé</ActionButton>
            {data?.peut_modifier && <ActionButton onClick={() => changerPart(a)} disabled={enregistrer.isPending}>Part du capital</ActionButton>}
          </>
        )} />
      {data?.associes.length === 0 && <p className="text-sm text-muted">Aucun associé : ajoutez-les dans Finance → Dépenses, onglet Associés.</p>}
      {releve && <Releve associe={releve} onFermer={() => setReleve(null)} />}

      <p className="text-xs text-muted">
        Un compte courant d&apos;associé n&apos;est jamais débiteur (statuts, art. 19) : le grand livre refuse un remboursement supérieur
        à ce que Kwa-Ba doit, ou l&apos;annulation d&apos;une avance déjà remboursée. L&apos;écriture d&apos;ouverture du capital sera passée
        avec l&apos;expert-comptable, au premier bilan.
      </p>
    </div>
  );
}

function Releve({ associe, onFermer }: { associe: CompteCourantAssocie; onFermer: () => void }) {
  const { data, isLoading, isError, error } = useReleveAssocie(associe.id);
  const colonnes: Colonne<LigneCompteCourant>[] = [
    { titre: "Date", cellule: (l) => <span className="whitespace-nowrap">{formatDate(l.date)}</span>, masquerMobile: true },
    { titre: "Pièce", cellule: (l) => <span className="whitespace-nowrap">{l.piece || "—"}</span> },
    { titre: "Libellé", cellule: (l) => (
      <span className="block min-w-0"><span className="block">{l.libelle || l.nature_libelle}</span>
        <span className="text-xs text-muted">{l.nature} · {l.nature_libelle}{l.annule_mouvement_id && " · ligne inverse"}</span></span>
    ) },
    { titre: "Montant", cellule: (l) => <span className={cn("tabular-nums whitespace-nowrap", l.montant_signe < 0 && "text-red-700")}>{l.montant_signe > 0 ? "+" : ""}{formatPrice(l.montant_signe)}</span>, className: "text-right" },
    { titre: "Solde", cellule: (l) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(l.solde)}</strong>, className: "text-right" },
  ];
  return (
    <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label="Relevé du compte courant">
      <div className="flex flex-wrap justify-between gap-2">
        <h2 className="font-heading font-bold text-dark">Compte courant · {associe.nom}</h2>
        <div className="flex items-center gap-3">
          {data && <Pill ton={data.solde > 0 ? "bleu" : "gris"}>Kwa-Ba doit {formatPrice(data.solde)}</Pill>}
          <button onClick={onFermer} className="text-sm font-semibold text-brand">Fermer</button>
        </div>
      </div>
      {isError && <ErreurLecture erreur={error} />}
      <AdminTable colonnes={colonnes} lignes={data?.lignes} cle={(l) => String(l.mouvement_id)} chargement={isLoading}
        titreMobile={(l) => <span className="flex justify-between gap-2">{formatDate(l.date)}<span className="tabular-nums">{formatPrice(l.montant_signe)}</span></span>} />
      {data?.lignes.length === 0 && <p className="text-sm text-muted">Aucune ligne : cet associé n&apos;a encore rien avancé.</p>}
    </section>
  );
}
