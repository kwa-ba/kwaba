"use client";

import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, CircleDashed, Download, FileWarning, Paperclip, RefreshCw, XCircle } from "lucide-react";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { messageErreurPdf, telechargerPdf } from "@/lib/documents";
import { cn, formatDate, formatPrice, isoDate } from "@/lib/utils";
import { urlJustificatif, type EtatOperation, type EtatRapprochement, type JourRapprochement, type OperationRapprochee,
  type RegularisationFinance } from "../api";
import { useImporterRapprochement, useJustificatifs, useRapprochementJour, useRapprochements, useReferentielsFinance,
  useRegulariser } from "../hooks";
import { CHAMP, ErreurLecture, libelleMois } from "./communs";

const ETATS_JOUR: Record<EtatRapprochement, { libelle: string; ton: "vert" | "rouge" | "gris"; icone: typeof CheckCircle2 }> = {
  fait: { libelle: "Rapproché", ton: "vert", icone: CheckCircle2 },
  en_erreur: { libelle: "En écart", ton: "rouge", icone: XCircle },
  non_fait: { libelle: "Non importé", ton: "gris", icone: CircleDashed },
};
const ETATS_OPERATION: Record<EtatOperation, { libelle: string; ton: "vert" | "rouge" | "bleu" | "gris" }> = {
  concorde: { libelle: "Concorde", ton: "vert" },
  ecart: { libelle: "Écart", ton: "rouge" },
  regularisee: { libelle: "Régularisée", ton: "bleu" },
  hors_livre: { libelle: "Hors grand livre", ton: "gris" },
};
const TYPES: Record<OperationRapprochee["type"], string> = {
  encaissement: "Paiement", remboursement: "Remboursement", versement: "Versement à l'hôte", inconnu: "Inconnue de Kwa-Ba",
};

function jourLong(jour: string) {
  return new Date(`${jour}T12:00:00`).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
}

function Montant({ valeur, signe }: { valeur: number | null | undefined; signe?: boolean }) {
  if (valeur === null || valeur === undefined) return <span className="text-muted">—</span>;
  return <span className="tabular-nums whitespace-nowrap">{signe && valeur > 0 ? "+" : ""}{formatPrice(valeur)}</span>;
}

/**
 * Reconciliation with FedaPay (GL-12): each finished day compared on three sides, Kwa-Ba's records, the FEDAPAY
 * account of the ledger and FedaPay's statement with its real fees (written as D01). A day is green only when every
 * operation agrees and the gap is zero; a day never imported is never a zero gap. Every day of a month must be green
 * before it can be closed.
 */
export default function Rapprochement() {
  const [mois, setMois] = useState(() => isoDate(new Date()).slice(0, 7));
  const [jour, setJour] = useState<string | null>(null);
  const [compte, setCompte] = useState("FEDAPAY");
  const { data, isLoading, isError, error } = useRapprochements(`${mois}-01`, compte);
  // FedaPay is read through its API; a bank account through its imported statement (Finance → Virements)
  const peutImporter = !!data?.peut_importer && compte === "FEDAPAY";
  const releve = compte === "FEDAPAY" ? "FedaPay" : "Relevé";
  const importer = useImporterRapprochement();

  const importerPeriode = (debut: string, fin: string) => {
    importer.mutate({ debut, fin }, {
      onSuccess: (r) => {
        const rouges = r.jours.filter((j) => j.etat !== "fait").length;
        if (rouges) toast.warning(`${r.jours.length} journée(s) importée(s), ${rouges} en écart.`);
        else toast.success(`${r.jours.length} journée(s) importée(s) : tout concorde.`);
        const remarque = r.jours.find((j) => j.remarque)?.remarque;
        if (remarque) toast.info(remarque);
      },
      onError: (err) => toast.error(apiErrorMessage(err, "Import impossible.")),
    });
  };
  const jours = data?.jours ?? [];
  const colonnes: Colonne<JourRapprochement>[] = [
    { titre: "Journée", cellule: (j) => <strong className="whitespace-nowrap capitalize">{jourLong(j.jour)}</strong>, masquerMobile: true },
    { titre: "État", cellule: (j) => {
      const e = ETATS_JOUR[j.etat];
      return <span><Pill ton={e.ton}><e.icone size={12} aria-hidden />{e.libelle}</Pill>
        {j.message && <span className="block text-xs text-muted mt-1 max-w-72">{j.message}</span>}</span>;
    } },
    { titre: "Kwa-Ba", cellule: (j) => <Montant valeur={j.etat === "non_fait" ? null : j.solde_kwaba} signe />, className: "text-right" },
    { titre: "Grand livre", cellule: (j) => <Montant valeur={j.etat === "non_fait" ? null : j.solde_livre} signe />, className: "text-right" },
    { titre: `${releve} (net)`, cellule: (j) => <Montant valeur={j.etat === "non_fait" ? null : j.solde_externe} signe />, className: "text-right" },
    { titre: "Frais réels", cellule: (j) => <Montant valeur={j.etat === "non_fait" ? null : j.frais} />, className: "text-right" },
    { titre: "Écart", cellule: (j) => j.etat === "non_fait" ? <span className="text-muted">—</span>
      : <strong className={cn("tabular-nums", j.ecart ? "text-red-700" : "text-green-700")}>{formatPrice(j.ecart ?? 0)}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-3">
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Mois</span>
          <input type="month" className={CHAMP} value={mois} max={isoDate(new Date()).slice(0, 7)}
            onChange={(e) => { if (e.target.value) { setMois(e.target.value); setJour(null); } }} /></label>
        {(data?.comptes?.length ?? 0) > 1 && (
          <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Compte</span>
            <select className={CHAMP} value={compte} onChange={(e) => { setCompte(e.target.value); setJour(null); }}>
              {data?.comptes?.map((c) => <option key={c.code} value={c.code}>{c.libelle}</option>)}
            </select></label>
        )}
        {peutImporter && jours.length > 0 && (
          <button onClick={() => importerPeriode(jours[jours.length - 1].jour, jours[0].jour)} disabled={importer.isPending}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
            <Download size={16} aria-hidden /> {importer.isPending ? "Lecture de FedaPay…" : `Importer ${libelleMois(`${mois}-01`)}`}
          </button>
        )}
      </div>

      {data && (
        <div className="grid grid-cols-3 gap-3">
          {(["fait", "en_erreur", "non_fait"] as const).map((etat) => (
            <div key={etat} className={cn("rounded-2xl p-3 sm:p-4 border", etat === "en_erreur" && data.resume[etat] ? "bg-red-50 border-red-200" : "bg-surface border-gray-100")}>
              <p className="text-xs font-semibold text-muted">{ETATS_JOUR[etat].libelle}</p>
              <p className="font-heading font-bold text-xl tabular-nums">{data.resume[etat]}</p>
            </div>
          ))}
        </div>
      )}
      {isError && <ErreurLecture erreur={error} />}
      {data && jours.length === 0 && <p className="text-sm text-muted">Aucune journée terminée dans ce mois.</p>}

      <AdminTable colonnes={colonnes} lignes={jours} cle={(j) => j.jour} chargement={isLoading}
        titreMobile={(j) => <span className="capitalize">{jourLong(j.jour)}</span>}
        actions={(j) => (
          <>
            {j.etat !== "non_fait" && <ActionButton onClick={() => setJour(j.jour)}>Détail</ActionButton>}
            {peutImporter && (
              <ActionButton onClick={() => importerPeriode(j.jour, j.jour)} disabled={importer.isPending}>
                <RefreshCw size={12} className="inline" aria-hidden /> {j.etat === "non_fait" ? "Importer" : "Réimporter"}
              </ActionButton>
            )}
          </>
        )} />

      {jour && <DetailJour jour={jour} compte={compte} peutRegulariser={!!data?.peut_regulariser} seuil={data?.seuil_double_validation ?? 0}
        onFermer={() => setJour(null)} />}

      <p className="text-xs text-muted">
        Chaque nuit, les trois dernières journées sont relues chez FedaPay. Les frais réels de FedaPay sont une charge de Kwa-Ba (D01, compte 6317),
        écrite au montant du relevé. L&apos;argent d&apos;un produit pas encore au grand livre (Kwa-Ba Give, transferts, locations) est montré à part et n&apos;entre pas dans l&apos;écart.
      </p>
    </div>
  );
}

function DetailJour({ jour, compte, peutRegulariser, seuil, onFermer }: {
  jour: string; compte: string; peutRegulariser: boolean; seuil: number; onFermer: () => void;
}) {
  const { data, isLoading, isError, error } = useRapprochementJour(jour, compte);
  const [cible, setCible] = useState<{ reference: string; montant: number; sens: "entree" | "sortie" } | null>(null);

  const colonnes: Colonne<OperationRapprochee>[] = [
    { titre: "Opération", cellule: (o) => (
      <span className="block min-w-0">
        <strong className="block">{TYPES[o.type]}</strong>
        <span className="text-xs text-muted break-all">{o.kwaba_reference || "—"} · FedaPay {o.reference}</span>
      </span>
    ), masquerMobile: true },
    { titre: "État", cellule: (o) => <span><Pill ton={ETATS_OPERATION[o.etat].ton}>{ETATS_OPERATION[o.etat].libelle}</Pill>
      {o.message && <span className="block text-xs text-muted mt-1 max-w-72">{o.message}</span>}</span> },
    { titre: "Kwa-Ba", cellule: (o) => <Montant valeur={o.kwaba_montant === null ? null : (o.sens === "sortie" ? -o.kwaba_montant : o.kwaba_montant)} signe />, className: "text-right" },
    { titre: "Grand livre", cellule: (o) => <Montant valeur={o.hors_grand_livre ? null : o.livre_montant} signe />, className: "text-right" },
    { titre: "FedaPay", cellule: (o) => o.externe_montant === null ? <span className="text-muted">Introuvable</span> : (
      <span className="block text-right">
        <Montant valeur={o.sens === "sortie" ? -o.externe_montant : o.externe_montant} signe />
        {!!o.externe_frais && <span className="block text-xs text-muted">frais {formatPrice(o.externe_frais)}</span>}
      </span>
    ), className: "text-right" },
  ];

  return (
    <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-4" aria-label={`Rapprochement du ${jour}`}>
      <div className="flex justify-between gap-2">
        <h2 className="font-heading font-bold text-dark capitalize">{jourLong(jour)} · trois colonnes</h2>
        <button onClick={onFermer} className="text-sm font-semibold text-brand">Fermer</button>
      </div>
      {isError && <ErreurLecture erreur={error} />}
      {data && (
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div><dt className="text-xs text-muted">Grand livre</dt><dd><Montant valeur={data.jour.solde_livre} signe /></dd></div>
          <div><dt className="text-xs text-muted">FedaPay net</dt><dd><Montant valeur={data.jour.solde_externe} signe /></dd></div>
          <div><dt className="text-xs text-muted">Mouvements internes</dt><dd><Montant valeur={data.jour.internes ?? 0} signe /></dd></div>
          <div><dt className="text-xs text-muted">Hors grand livre</dt><dd><Montant valeur={data.jour.hors_grand_livre ?? 0} signe /></dd></div>
        </dl>
      )}
      <AdminTable colonnes={colonnes} lignes={data?.operations} cle={(o) => o.reference} chargement={isLoading}
        titreMobile={(o) => <span>{TYPES[o.type]} · {o.kwaba_reference || o.reference}</span>}
        actions={(o) => peutRegulariser && o.etat === "ecart" ? (
          <ActionButton onClick={() => setCible({ reference: o.reference, sens: o.sens,
            montant: Math.abs((o.externe_montant === null ? 0 : (o.sens === "sortie" ? -(o.externe_montant + (o.externe_frais ?? 0)) : o.externe_montant - (o.externe_frais ?? 0))) - o.livre_montant) })}>
            <FileWarning size={12} className="inline" aria-hidden /> Régulariser
          </ActionButton>
        ) : null} />
      {data?.operations.length === 0 && <p className="text-sm text-muted">Aucune opération FedaPay ce jour.</p>}
      {peutRegulariser && data && data.jour.etat === "en_erreur" && !cible && (
        <button onClick={() => setCible({ reference: "", montant: Math.abs(data.jour.ecart ?? 0), sens: (data.jour.ecart ?? 0) > 0 ? "sortie" : "entree" })}
          className="text-sm font-semibold text-brand">Régulariser la journée elle-même (mouvements internes)</button>
      )}
      {cible && <FormRegularisation jour={jour} compte={compte} cible={cible} seuil={seuil} onFermer={() => setCible(null)} />}
      {!!data?.regularisations.length && <Regularisations lignes={data.regularisations} />}
    </section>
  );
}

function FormRegularisation({ jour, compte, cible, seuil, onFermer }: {
  jour: string; compte: string; cible: { reference: string; montant: number; sens: "entree" | "sortie" }; seuil: number; onFermer: () => void;
}) {
  const { data: ref } = useReferentielsFinance();
  const regulariser = useRegulariser();
  const [nature, setNature] = useState("D01");
  const [offre, setOffre] = useState("COURTE_DUREE");
  const [sens, setSens] = useState<"entree" | "sortie">(cible.sens === "entree" ? "entree" : "sortie");
  const [montant, setMontant] = useState(String(cible.montant || ""));
  const [motif, setMotif] = useState("");
  const [fichiers, setFichiers] = useState<File[]>([]);

  const envoyer = (e: React.FormEvent) => {
    e.preventDefault();
    regulariser.mutate({ jour, compte, regularisation: { reference: cible.reference, nature, offre, sens, montant: Number(montant), motif, fichiers } }, {
      onSuccess: (r) => {
        toast.success(r.attente_validation ? "Demande enregistrée : une seconde personne doit la valider (Finance → Validations)."
          : "Régularisation écrite au grand livre.");
        onFermer();
      },
      onError: (err) => toast.error(apiErrorMessage(err, "Régularisation refusée.")),
    });
  };

  return (
    <form onSubmit={envoyer} className="rounded-2xl border border-gray-100 bg-gray-50/60 p-4 space-y-3">
      <p className="text-sm font-semibold text-dark">
        Régulariser {cible.reference ? `l'opération ${cible.reference}` : "la journée"} · une ligne au grand livre, définitive
      </p>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Nature</span>
          <select className={cn(CHAMP, "w-full")} value={nature} onChange={(e) => setNature(e.target.value)} required>
            {ref?.natures.filter((n) => n.actif).map((n) => <option key={n.code} value={n.code}>{n.code} · {n.libelle}</option>)}
          </select></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Offre</span>
          <select className={cn(CHAMP, "w-full")} value={offre} onChange={(e) => setOffre(e.target.value)} required>
            {ref?.offres.filter((o) => o.active).map((o) => <option key={o.code} value={o.code}>{o.libelle}</option>)}
          </select></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Sens sur le compte FedaPay</span>
          <select className={cn(CHAMP, "w-full")} value={sens} onChange={(e) => setSens(e.target.value as "entree" | "sortie")}>
            <option value="entree">Entrée</option><option value="sortie">Sortie</option>
          </select></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Montant (F CFA)</span>
          <input type="number" min={1} step={1} inputMode="numeric" className={cn(CHAMP, "w-full")} value={montant}
            onChange={(e) => setMontant(e.target.value)} required /></label>
      </div>
      <label className="text-sm block"><span className="block text-xs font-semibold text-muted mb-1">Motif (reste au grand livre)</span>
        <textarea className={cn(CHAMP, "w-full")} rows={2} minLength={10} value={motif} onChange={(e) => setMotif(e.target.value)} required
          placeholder="Ex. : frais FedaPay non annoncés sur ce paiement, confirmés par le support le 19/11" /></label>
      <label className="text-sm block"><span className="block text-xs font-semibold text-muted mb-1">Pièces justificatives (PDF ou image, obligatoire)</span>
        <input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" required
          onChange={(e) => setFichiers(Array.from(e.target.files ?? []))} className="text-sm" /></label>
      {seuil > 0 && Number(montant) >= seuil && (
        <p className="text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">À partir de {formatPrice(seuil)}, une seconde personne valide avant l&apos;écriture.</p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={regulariser.isPending || !fichiers.length}
          className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
          {regulariser.isPending ? "Envoi…" : "Écrire la régularisation"}
        </button>
        <button type="button" onClick={onFermer} className="px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Annuler</button>
      </div>
    </form>
  );
}

const STATUTS_REGUL: Record<RegularisationFinance["statut"], { libelle: string; ton: "vert" | "orange" | "gris" }> = {
  ecrite: { libelle: "Écrite", ton: "vert" }, en_attente: { libelle: "En attente de validation", ton: "orange" },
  refusee: { libelle: "Refusée", ton: "gris" },
};

function Regularisations({ lignes }: { lignes: RegularisationFinance[] }) {
  const [ouverte, setOuverte] = useState<string | null>(null);
  return (
    <div className="space-y-2">
      <h3 className="font-heading font-bold text-dark text-sm">Régularisations</h3>
      <ul className="text-sm divide-y divide-gray-100">
        {lignes.map((r) => (
          <li key={r.id} className="py-2 space-y-1">
            <div className="flex flex-wrap justify-between gap-2">
              <span><strong>{r.nature}</strong> · {r.sens === "entree" ? "entrée" : "sortie"} <span className="tabular-nums">{formatPrice(r.montant)}</span>
                {r.reference && <span className="text-muted"> · {r.reference}</span>}</span>
              <Pill ton={STATUTS_REGUL[r.statut].ton}>{STATUTS_REGUL[r.statut].libelle}</Pill>
            </div>
            <p className="text-muted">{r.motif} · {r.demandee_par || "—"}, {formatDate(r.demandee_le)}</p>
            <button onClick={() => setOuverte(ouverte === r.id ? null : r.id)} className="text-xs font-semibold text-brand inline-flex items-center gap-1">
              <Paperclip size={12} aria-hidden /> Pièces
            </button>
            {ouverte === r.id && <Pieces id={r.id} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Pieces({ id }: { id: string }) {
  const { data, isLoading } = useJustificatifs("regularisation", id);
  if (isLoading) return <div className="h-8 skeleton rounded-lg" />;
  return (
    <ul className="text-xs space-y-1">
      {data?.map((j) => (
        <li key={j.id} className="flex justify-between gap-2">
          <span>{j.nom}</span>
          <ActionButton onClick={async () => {
            try { await telechargerPdf(urlJustificatif(j.id), j.nom); } catch (err) { toast.error(await messageErreurPdf(err, "Téléchargement impossible.")); }
          }}>Ouvrir</ActionButton>
        </li>
      ))}
    </ul>
  );
}
