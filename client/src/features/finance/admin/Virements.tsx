"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ArrowRightLeft, Landmark, Upload } from "lucide-react";
import AdminTable, { ActionButton, Pagination, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice, isoDate } from "@/lib/utils";
import type { ColonnesReleve, CompteArgentFinance, ListeVirements, StatutVirement, VirementFinance } from "../api";
import { useActiverCompteArgent, useAnnulerVirement, useImporterReleve, useSaisirVirement, useVirements } from "../hooks";
import { CHAMP, ErreurLecture } from "./communs";

const STATUTS: Record<StatutVirement, { libelle: string; ton: "vert" | "orange" | "gris" | "rouge" }> = {
  ecrit: { libelle: "Au grand livre", ton: "vert" },
  en_attente: { libelle: "En attente de validation", ton: "orange" },
  refuse: { libelle: "Refusé", ton: "rouge" },
  annule: { libelle: "Annulé", ton: "gris" },
};

/**
 * Internal transfers and bank statements (GL-22): the money accounts (the bank account is opened here the day it
 * exists), each transfer between two of them with its proof (two V01 lines, 585 back to zero), and the CSV statement of
 * the bank, matched with the transfers and reconciled day by day (Finance → Rapprochement, account « bank »).
 */
export default function Virements() {
  const [page, setPage] = useState(1);
  const [saisie, setSaisie] = useState(false);
  const { data, isLoading, isError, error } = useVirements(page);
  const annuler = useAnnulerVirement();
  const ouverts = (data?.comptes ?? []).filter((c) => c.actif && !c.sans_releve);

  const demanderAnnulation = (v: VirementFinance) => {
    const motif = window.prompt(`Annuler ${v.numero} (${formatPrice(v.montant)}) : motif ?`);
    if (!motif) return;
    annuler.mutate({ id: v.id, motif }, {
      onSuccess: () => toast.success(`${v.numero} annulé : deux lignes inverses au grand livre.`),
      onError: (err) => toast.error(apiErrorMessage(err, "Annulation refusée.")),
    });
  };

  const colonnes: Colonne<VirementFinance>[] = [
    { titre: "Pièce", cellule: (v) => <span className="block"><strong className="whitespace-nowrap">{v.numero}</strong>
      <span className="block text-xs text-muted">{formatDate(v.date_virement)}</span></span>, masquerMobile: true },
    { titre: "Virement", cellule: (v) => <span className="block min-w-0"><span className="block">{v.source_libelle} → {v.destination_libelle}</span>
      <span className="text-xs text-muted">{v.motif}{v.reference_externe && ` · réf. ${v.reference_externe}`}</span></span> },
    { titre: "Statut", cellule: (v) => <span><Pill ton={STATUTS[v.statut].ton}>{STATUTS[v.statut].libelle}</Pill>
      {v.motif_annulation && <span className="block text-xs text-muted mt-1 max-w-60">{v.motif_annulation}</span>}</span> },
    { titre: "Montant", cellule: (v) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(v.montant)}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-5">
      {isError && <ErreurLecture erreur={error} />}
      {data && <Comptes donnees={data} />}

      <section className="space-y-3" aria-label="Virements internes">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-heading font-bold text-dark flex items-center gap-2"><ArrowRightLeft size={16} aria-hidden /> Virements internes</h2>
          {data?.peut_saisir && !saisie && (
            <button onClick={() => setSaisie(true)} disabled={ouverts.length < 2}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
              Saisir un virement
            </button>
          )}
        </div>
        {data && ouverts.length < 2 && (
          <p className="text-sm bg-amber-50 text-amber-900 rounded-xl px-4 py-3">Un virement va d&apos;un compte à un autre : il faut au moins deux comptes ouverts (FedaPay et la banque, une fois ouverte ci-dessus).</p>
        )}
        {saisie && data && <FormVirement comptes={ouverts} seuil={data.seuil} onFermer={() => setSaisie(false)} />}
        <AdminTable colonnes={colonnes} lignes={data?.results} cle={(v) => v.id} chargement={isLoading}
          titreMobile={(v) => <span className="flex justify-between gap-2">{v.numero}<span className="tabular-nums">{formatPrice(v.montant)}</span></span>}
          actions={(v) => data?.peut_saisir && v.statut === "ecrit"
            ? <ActionButton danger onClick={() => demanderAnnulation(v)} disabled={annuler.isPending}>Annuler</ActionButton> : null} />
        {data && data.count > data.page_size && <Pagination page={page} count={data.count} pageSize={data.page_size} onChange={setPage} />}
        {data?.count === 0 && <p className="text-sm text-muted">Aucun virement pour l&apos;instant.</p>}
      </section>

      {data && <Releves donnees={data} />}
    </div>
  );
}

function Comptes({ donnees }: { donnees: ListeVirements }) {
  const activer = useActiverCompteArgent();
  const basculer = (c: CompteArgentFinance) => {
    const message = c.actif ? `Désactiver ${c.libelle} ?`
      : `Ouvrir ${c.libelle} dans l'appli ? Chaque journée devra ensuite être rapprochée avec son relevé, sinon la clôture sera refusée.`;
    if (!window.confirm(message)) return;
    activer.mutate({ code: c.code, actif: !c.actif }, {
      onSuccess: (r) => toast.success(r.actif ? `${r.libelle} ouvert : rapproché à partir d'aujourd'hui.` : `${r.libelle} désactivé.`),
      onError: (err) => toast.error(apiErrorMessage(err, "Changement refusé.")),
    });
  };
  const comptes = donnees.comptes.filter((c) => !c.sans_releve);
  return (
    <section className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-2" aria-label="Comptes d'argent">
      <h2 className="font-heading font-bold text-dark flex items-center gap-2"><Landmark size={16} aria-hidden /> Comptes d&apos;argent</h2>
      <ul className="text-sm divide-y divide-gray-50">
        {comptes.map((c) => (
          <li key={c.code} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="min-w-0"><strong className={cn(!c.actif && "text-muted")}>{c.libelle}</strong>
              <span className="block text-xs text-muted">{c.code} · compte {c.compte_syscohada}{c.actif_depuis ? ` · rapproché depuis le ${formatDate(c.actif_depuis)}` : ""}</span></span>
            <span className="flex items-center gap-3">
              {c.actif ? <span className="tabular-nums font-semibold">{formatPrice(c.solde)}</span> : <Pill ton="gris">Pas encore ouvert</Pill>}
              {donnees.peut_activer && c.banque && (c.actif ? !c.nb_lignes : true) && (
                <ActionButton onClick={() => basculer(c)} disabled={activer.isPending}>{c.actif ? "Désactiver" : "Ouvrir dans l'appli"}</ActionButton>
              )}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted">Le compte bancaire s&apos;ouvre ici le jour où il existe (super administrateur). Il est rapproché à partir de ce jour : ses relevés s&apos;importent ci-dessous.</p>
    </section>
  );
}

function FormVirement({ comptes, seuil, onFermer }: { comptes: CompteArgentFinance[]; seuil: number; onFermer: () => void }) {
  const saisir = useSaisirVirement();
  const [v, setV] = useState({ date_virement: isoDate(new Date()), source: comptes[0]?.code ?? "", destination: comptes[1]?.code ?? "",
    montant: "", motif: "", reference_externe: "" });
  const [fichiers, setFichiers] = useState<File[]>([]);
  const champ = (cle: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setV({ ...v, [cle]: e.target.value });
  const envoyer = (e: React.FormEvent) => {
    e.preventDefault();
    saisir.mutate({ ...v, montant: Number(v.montant), fichiers }, {
      onSuccess: (r) => { toast.success(r.attente_validation ? `${r.numero} : une deuxième personne doit le valider.` : `${r.numero} écrit au grand livre.`); onFermer(); },
      onError: (err) => toast.error(apiErrorMessage(err, "Virement refusé.")),
    });
  };
  return (
    <form onSubmit={envoyer} className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label="Saisir un virement">
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Date</span>
          <input type="date" required className={cn(CHAMP, "w-full")} max={isoDate(new Date())} value={v.date_virement} onChange={champ("date_virement")} /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Depuis</span>
          <select className={cn(CHAMP, "w-full")} value={v.source} onChange={champ("source")}>
            {comptes.map((c) => <option key={c.code} value={c.code}>{c.libelle}</option>)}</select></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Vers</span>
          <select className={cn(CHAMP, "w-full")} value={v.destination} onChange={champ("destination")}>
            {comptes.map((c) => <option key={c.code} value={c.code}>{c.libelle}</option>)}</select></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Montant (F CFA)</span>
          <input type="number" required min={1} step={1} inputMode="numeric" className={cn(CHAMP, "w-full")} value={v.montant} onChange={champ("montant")} /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Référence (FedaPay ou banque)</span>
          <input maxLength={60} className={cn(CHAMP, "w-full")} value={v.reference_externe} onChange={champ("reference_externe")} placeholder="Obligatoire pour FedaPay" /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Motif</span>
          <input required minLength={5} maxLength={300} className={cn(CHAMP, "w-full")} value={v.motif} onChange={champ("motif")} placeholder="Ex. : retrait des commissions de novembre" /></label>
      </div>
      <label className="text-sm block"><span className="block text-xs font-semibold text-muted mb-1">Preuve (avis de la banque, reçu du prestataire : PDF ou image, obligatoire)</span>
        <input type="file" multiple required accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(e) => setFichiers(Array.from(e.target.files ?? []))} className="text-sm" /></label>
      {seuil > 0 && Number(v.montant) >= seuil && (
        <p className="text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">À partir de {formatPrice(seuil)}, une deuxième personne valide avant l&apos;écriture.</p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={saisir.isPending || !fichiers.length} className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
          {saisir.isPending ? "Envoi…" : "Enregistrer le virement"}</button>
        <button type="button" onClick={onFermer} className="px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Annuler</button>
      </div>
    </form>
  );
}

const COLONNES_PAR_DEFAUT: ColonnesReleve = { date: "Date", libelle: "Libellé", debit: "Débit", credit: "Crédit", montant: "", reference: "" };

function Releves({ donnees }: { donnees: ListeVirements }) {
  const importer = useImporterReleve();
  const banques = donnees.comptes.filter((c) => c.banque && c.actif);
  const [compte, setCompte] = useState(banques[0]?.code ?? "");
  const [fichier, setFichier] = useState<File | null>(null);
  const [colonnes, setColonnes] = useState<ColonnesReleve>(COLONNES_PAR_DEFAUT);
  const col = (cle: keyof ColonnesReleve) => (e: React.ChangeEvent<HTMLInputElement>) => setColonnes({ ...colonnes, [cle]: e.target.value });
  const envoyer = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fichier) return;
    importer.mutate({ compte, fichier, colonnes }, {
      onSuccess: (r) => {
        const rouges = r.jours.filter((j) => j.etat !== "fait").length;
        const texte = `${r.lignes} ligne(s) du ${formatDate(r.debut)} au ${formatDate(r.fin)} : ${r.rapprochees} rapprochée(s), ${r.inconnues} à expliquer.`;
        if (rouges) toast.warning(`${texte} ${rouges} journée(s) en écart : voir Finance → Rapprochement.`);
        else toast.success(texte);
      },
      onError: (err) => toast.error(apiErrorMessage(err, "Import refusé.")),
    });
  };
  return (
    <section className="space-y-3" aria-label="Relevés bancaires">
      <h2 className="font-heading font-bold text-dark flex items-center gap-2"><Upload size={16} aria-hidden /> Relevés bancaires</h2>
      {!banques.length ? <p className="text-sm text-muted">Aucun compte bancaire ouvert dans l&apos;appli : ses relevés s&apos;importeront ici.</p> : donnees.peut_saisir && (
        <form onSubmit={envoyer} className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-3">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Compte</span>
              <select className={cn(CHAMP, "w-full")} value={compte} onChange={(e) => setCompte(e.target.value)}>
                {banques.map((c) => <option key={c.code} value={c.code}>{c.libelle}</option>)}</select></label>
            <label className="text-sm min-w-0 sm:col-span-2"><span className="block text-xs font-semibold text-muted mb-1">Relevé exporté par la banque (CSV, jusqu&apos;à hier)</span>
              <input type="file" required accept=".csv,text/csv,text/plain" onChange={(e) => setFichier(e.target.files?.[0] ?? null)} className="text-sm" /></label>
          </div>
          <p className="text-xs text-muted">Noms des colonnes, tels qu&apos;ils figurent sur la première ligne du fichier. Débit et crédit, ou un seul montant signé.</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {([["date", "Date"], ["libelle", "Libellé"], ["debit", "Débit"], ["credit", "Crédit"], ["montant", "Montant signé"], ["reference", "Référence"]] as const).map(([cle, libelle]) => (
              <label key={cle} className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">{libelle}</span>
                <input className={cn(CHAMP, "w-full")} value={colonnes[cle]} onChange={col(cle)} /></label>
            ))}
          </div>
          <button type="submit" disabled={importer.isPending || !fichier} className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
            {importer.isPending ? "Lecture…" : "Importer et rapprocher"}</button>
        </form>
      )}
      {donnees.releves.length > 0 && (
        <ul className="bg-surface rounded-2xl border border-gray-100 divide-y divide-gray-50 text-sm">
          {donnees.releves.map((r) => (
            <li key={r.id} className="flex flex-wrap justify-between gap-2 p-3">
              <span><strong>{r.nom_fichier}</strong> <span className="text-muted">· {r.compte_argent_id} · du {formatDate(r.debut)} au {formatDate(r.fin)}</span></span>
              <span className="text-muted">{r.nb_lignes} ligne(s) · importé le {formatDate(r.importe_le)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">
        Chaque ligne du relevé est rapprochée du virement qu&apos;elle est : par sa référence, ou par son montant à 3 jours près.
        Une ligne que rien n&apos;explique (frais bancaires, versement inconnu) laisse sa journée en écart : elle se régularise dans Finance → Rapprochement, compte bancaire.
      </p>
    </section>
  );
}
