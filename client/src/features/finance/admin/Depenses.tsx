"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Paperclip, Plus } from "lucide-react";
import AdminTable, { ActionButton, Pagination, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { messageErreurPdf, telechargerPdf } from "@/lib/documents";
import { cn, formatDate, formatPrice, isoDate } from "@/lib/utils";
import { urlJustificatif, type DepenseFinance, type FiltresDepenses, type StatutDepense } from "../api";
import { useAnnulerDepense, useAssocies, useDepenses, useEnregistrerAssocie, useEnregistrerFournisseur, useFournisseurs,
  useJustificatifs, useReferentielsFinance, useSaisirDepense } from "../hooks";
import { CHAMP, ChoixCode, ErreurLecture } from "./communs";

const STATUTS: Record<StatutDepense, { libelle: string; ton: "vert" | "orange" | "gris" | "rouge" }> = {
  ecrite: { libelle: "Au grand livre", ton: "vert" },
  en_attente: { libelle: "En attente de validation", ton: "orange" },
  refusee: { libelle: "Refusée", ton: "rouge" },
  annulee: { libelle: "Annulée", ton: "gris" },
};
const ONGLETS = [["depenses", "Dépenses"], ["fournisseurs", "Fournisseurs"], ["associes", "Associés"]] as const;

/**
 * Expenses of Kwa-Ba (GL-15): each charge entered with its evidence (invoice, receipt), numbered DEP-YYYY-NNNNN and
 * written in the ledger: the charge by supplier, and what Kwa-Ba owes the associate who advanced it (compte courant).
 * From the threshold a second person approves it first. A written expense is cancelled by inverse lines.
 */
export default function Depenses() {
  const [onglet, setOnglet] = useState<(typeof ONGLETS)[number][0]>("depenses");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2" role="tablist">
        {ONGLETS.map(([code, libelle]) => (
          <button key={code} role="tab" aria-selected={onglet === code} onClick={() => setOnglet(code)}
            className={cn("px-3 py-1.5 rounded-lg text-sm font-semibold border",
              onglet === code ? "border-primary text-brand bg-primary/5" : "border-gray-200 text-dark hover:bg-gray-50")}>
            {libelle}
          </button>
        ))}
      </div>
      {onglet === "depenses" && <ListeDepenses />}
      {onglet === "fournisseurs" && <Annuaire genre="fournisseurs" />}
      {onglet === "associes" && <Annuaire genre="associes" />}
    </div>
  );
}

function ListeDepenses() {
  const [filtres, setFiltres] = useState<FiltresDepenses>({});
  const [page, setPage] = useState(1);
  const [saisie, setSaisie] = useState(false);
  const [pieces, setPieces] = useState<DepenseFinance | null>(null);
  const { data, isLoading, isError, error } = useDepenses(filtres, page);
  const { data: ref } = useReferentielsFinance();
  const annuler = useAnnulerDepense();
  const natures = (ref?.natures ?? []).filter((n) => n.famille === "D" && n.actif);

  const filtrer = (champ: keyof FiltresDepenses, valeur: string) => { setFiltres((f) => ({ ...f, [champ]: valeur })); setPage(1); };
  const demanderAnnulation = (d: DepenseFinance) => {
    const motif = window.prompt(`Annuler ${d.numero} (${formatPrice(d.montant)}) : motif ?`);
    if (!motif) return;
    annuler.mutate({ id: d.id, motif }, {
      onSuccess: () => toast.success(`${d.numero} annulée : deux lignes inverses au grand livre.`),
      onError: (err) => toast.error(apiErrorMessage(err, "Annulation refusée.")),
    });
  };

  const colonnes: Colonne<DepenseFinance>[] = [
    { titre: "Pièce", cellule: (d) => <span className="block"><strong className="whitespace-nowrap">{d.numero}</strong>
      <span className="block text-xs text-muted">{formatDate(d.date_depense)}</span></span>, masquerMobile: true },
    { titre: "Dépense", cellule: (d) => <span className="block min-w-0"><span className="block">{d.libelle}</span>
      <span className="text-xs text-muted">{d.nature} · {d.fournisseur}{d.reference_facture && ` · facture ${d.reference_facture}`}</span></span> },
    { titre: "Avancée par", cellule: (d) => d.associe || "—" },
    { titre: "Statut", cellule: (d) => <span><Pill ton={STATUTS[d.statut].ton}>{STATUTS[d.statut].libelle}</Pill>
      {d.motif_annulation && <span className="block text-xs text-muted mt-1 max-w-60">{d.motif_annulation}</span>}</span> },
    { titre: "Montant", cellule: (d) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(d.montant)}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-3">
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Du</span>
          <input type="date" className={CHAMP} value={filtres.debut ?? ""} onChange={(e) => filtrer("debut", e.target.value)} /></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Au</span>
          <input type="date" className={CHAMP} value={filtres.fin ?? ""} onChange={(e) => filtrer("fin", e.target.value)} /></label>
        <ChoixCode libelle="Nature" valeur={filtres.nature ?? ""} onChange={(v) => filtrer("nature", v)} options={natures} tous="Toutes" />
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Statut</span>
          <select className={CHAMP} value={filtres.statut ?? ""} onChange={(e) => filtrer("statut", e.target.value)}>
            <option value="">Tous</option>
            {(Object.keys(STATUTS) as StatutDepense[]).map((s) => <option key={s} value={s}>{STATUTS[s].libelle}</option>)}
          </select></label>
        {data?.peut_saisir && (
          <button onClick={() => setSaisie(true)} className="sm:ml-auto inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold">
            <Plus size={16} aria-hidden /> Saisir une dépense
          </button>
        )}
      </div>

      {data && (
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="rounded-2xl p-4 bg-surface border border-gray-100">
            <p className="text-xs font-semibold text-muted">Dépenses au grand livre (sélection)</p>
            <p className="font-heading font-bold text-xl tabular-nums">{formatPrice(data.montant_ecrit)}</p>
          </div>
          <div className="rounded-2xl p-4 bg-surface border border-gray-100">
            <p className="text-xs font-semibold text-muted">Double validation</p>
            <p className="text-sm text-dark mt-1">{data.seuil ? `À partir de ${formatPrice(data.seuil)}, une deuxième personne valide (Finance → Validations).` : "Aucun seuil : chaque dépense est écrite tout de suite."}</p>
          </div>
        </div>
      )}
      {data && !data.peut_saisir && (
        <p className="text-sm bg-amber-50 text-amber-900 rounded-xl px-4 py-3">Consultation seulement : saisir une dépense demande la permission « Opérations financières ».</p>
      )}
      {saisie && <FormDepense seuil={data?.seuil ?? 0} onFermer={() => setSaisie(false)} />}
      {isError && <ErreurLecture erreur={error} />}

      <AdminTable colonnes={colonnes} lignes={data?.results} cle={(d) => d.id} chargement={isLoading}
        titreMobile={(d) => <span className="flex justify-between gap-2">{d.numero}<span className="tabular-nums">{formatPrice(d.montant)}</span></span>}
        actions={(d) => (
          <>
            <ActionButton onClick={() => setPieces(d)}><Paperclip size={12} className="inline" aria-hidden /> Pièces</ActionButton>
            {data?.peut_saisir && d.statut === "ecrite" && <ActionButton danger onClick={() => demanderAnnulation(d)} disabled={annuler.isPending}>Annuler</ActionButton>}
          </>
        )} />
      {data && data.count > data.page_size && <Pagination page={page} count={data.count} pageSize={data.page_size} onChange={setPage} />}
      {data?.count === 0 && <p className="text-sm text-muted">Aucune dépense pour ces filtres.</p>}
      {pieces && <Pieces depense={pieces} onFermer={() => setPieces(null)} />}
      <p className="text-xs text-muted">
        Aujourd&apos;hui, chaque dépense est avancée par un associé : la charge entre au résultat et Kwa-Ba lui doit la somme (compte courant 462).
        Son remboursement à l&apos;associé viendra avec les comptes courants (GL-16). Montants TTC : la TVA n&apos;est pas encore suivie.
      </p>
    </div>
  );
}

function FormDepense({ seuil, onFermer }: { seuil: number; onFermer: () => void }) {
  const { data: ref } = useReferentielsFinance();
  const { data: fournisseurs } = useFournisseurs();
  const { data: associes } = useAssocies();
  const saisir = useSaisirDepense();
  const [d, setD] = useState({ date_depense: isoDate(new Date()), nature: "D10", offre: "STRUCTURE", montant: "", libelle: "",
    fournisseur: "", associe: "", reference_facture: "" });
  const [fichiers, setFichiers] = useState<File[]>([]);
  const champ = (cle: keyof typeof d) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setD({ ...d, [cle]: e.target.value });

  const envoyer = (e: React.FormEvent) => {
    e.preventDefault();
    saisir.mutate({ ...d, montant: Number(d.montant), fichiers }, {
      onSuccess: (r) => {
        toast.success(r.attente_validation ? `${r.numero} enregistrée : une deuxième personne doit la valider.` : `${r.numero} écrite au grand livre.`);
        onFermer();
      },
      onError: (err) => toast.error(apiErrorMessage(err, "Dépense refusée.")),
    });
  };
  const actifs = <T extends { actif: boolean }>(l?: T[]) => (l ?? []).filter((x) => x.actif);

  return (
    <form onSubmit={envoyer} className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label="Saisir une dépense">
      <h2 className="font-heading font-bold text-dark">Nouvelle dépense</h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Date de la dépense</span>
          <input type="date" required className={cn(CHAMP, "w-full")} max={isoDate(new Date())} value={d.date_depense} onChange={champ("date_depense")} /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Nature</span>
          <select required className={cn(CHAMP, "w-full")} value={d.nature} onChange={champ("nature")}>
            {(ref?.natures ?? []).filter((n) => n.famille === "D" && n.actif).map((n) => <option key={n.code} value={n.code}>{n.code} · {n.libelle}</option>)}
          </select></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Offre concernée</span>
          <select className={cn(CHAMP, "w-full")} value={d.offre} onChange={champ("offre")}>
            {(ref?.offres ?? []).filter((o) => o.active).map((o) => <option key={o.code} value={o.code}>{o.libelle}</option>)}
          </select></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Montant TTC (F CFA)</span>
          <input type="number" required min={1} step={1} inputMode="numeric" className={cn(CHAMP, "w-full")} value={d.montant} onChange={champ("montant")} /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Fournisseur</span>
          <select required className={cn(CHAMP, "w-full")} value={d.fournisseur} onChange={champ("fournisseur")}>
            <option value="">Choisir…</option>
            {actifs(fournisseurs).map((f) => <option key={f.id} value={f.id}>{f.nom}</option>)}
          </select></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Avancée par l&apos;associé</span>
          <select required className={cn(CHAMP, "w-full")} value={d.associe} onChange={champ("associe")}>
            <option value="">Choisir…</option>
            {actifs(associes).map((a) => <option key={a.id} value={a.id}>{a.nom}</option>)}
          </select></label>
        <label className="text-sm sm:col-span-2 min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Libellé</span>
          <input required minLength={3} maxLength={200} className={cn(CHAMP, "w-full")} value={d.libelle} onChange={champ("libelle")}
            placeholder="Ex. : hébergement du site, novembre 2026" /></label>
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">N° de facture du fournisseur</span>
          <input maxLength={60} className={cn(CHAMP, "w-full")} value={d.reference_facture} onChange={champ("reference_facture")} /></label>
      </div>
      <label className="text-sm block"><span className="block text-xs font-semibold text-muted mb-1">Justificatif (facture ou reçu, PDF ou image, obligatoire)</span>
        <input type="file" multiple required accept="application/pdf,image/jpeg,image/png,image/webp"
          onChange={(e) => setFichiers(Array.from(e.target.files ?? []))} className="text-sm" /></label>
      {!fournisseurs?.length && <p className="text-xs text-muted">Ajoutez d&apos;abord le fournisseur dans l&apos;onglet Fournisseurs.</p>}
      {!associes?.length && <p className="text-xs text-muted">Ajoutez d&apos;abord les associés dans l&apos;onglet Associés.</p>}
      {seuil > 0 && Number(d.montant) >= seuil && (
        <p className="text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">À partir de {formatPrice(seuil)}, une deuxième personne valide avant l&apos;écriture au grand livre.</p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={saisir.isPending || !fichiers.length} className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
          {saisir.isPending ? "Envoi…" : "Enregistrer la dépense"}
        </button>
        <button type="button" onClick={onFermer} className="px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Annuler</button>
      </div>
    </form>
  );
}

function Pieces({ depense, onFermer }: { depense: DepenseFinance; onFermer: () => void }) {
  const { data, isLoading } = useJustificatifs("depense", depense.id);
  return (
    <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-2" aria-label="Justificatifs">
      <div className="flex justify-between gap-2">
        <h2 className="font-heading font-bold text-dark">Justificatifs · {depense.numero}</h2>
        <button onClick={onFermer} className="text-sm font-semibold text-brand">Fermer</button>
      </div>
      {isLoading && <div className="h-12 skeleton rounded-xl" />}
      <ul className="text-sm divide-y divide-gray-50">
        {data?.map((j) => (
          <li key={j.id} className="flex justify-between gap-2 py-2">
            <span>{j.nom} <span className="text-muted">· {Math.ceil(j.taille / 1024)} Ko</span></span>
            <ActionButton onClick={async () => {
              try { await telechargerPdf(urlJustificatif(j.id), j.nom); } catch (err) { toast.error(await messageErreurPdf(err, "Téléchargement impossible.")); }
            }}>Ouvrir</ActionButton>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Annuaire({ genre }: { genre: "fournisseurs" | "associes" }) {
  const fournisseurs = useFournisseurs();
  const associes = useAssocies();
  const enregistrerF = useEnregistrerFournisseur();
  const enregistrerA = useEnregistrerAssocie();
  const [nom, setNom] = useState("");
  const [detail, setDetail] = useState("");
  const [nif, setNif] = useState("");
  const estFournisseur = genre === "fournisseurs";
  const lignes = estFournisseur ? fournisseurs.data : associes.data;

  const message = { onSuccess: () => { setNom(""); setDetail(""); setNif(""); toast.success("Enregistré."); },
    onError: (err: unknown) => toast.error(apiErrorMessage(err, "Enregistrement refusé.")) };
  const ajouter = (e: React.FormEvent) => {
    e.preventDefault();
    if (estFournisseur) enregistrerF.mutate({ nom, nif, contact: detail }, message);
    else enregistrerA.mutate({ nom, email: detail }, message);
  };
  const basculer = (id: string, nomActuel: string, actif: boolean) => {
    if (estFournisseur) enregistrerF.mutate({ id, nom: nomActuel, actif: !actif }, message);
    else enregistrerA.mutate({ id, nom: nomActuel, actif: !actif }, message);
  };

  return (
    <div className="space-y-4">
      <form onSubmit={ajouter} className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-3">
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Nom</span>
          <input required minLength={2} maxLength={120} className={CHAMP} value={nom} onChange={(e) => setNom(e.target.value)} /></label>
        {estFournisseur && (
          <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">NIF (facultatif)</span>
            <input maxLength={40} className={CHAMP} value={nif} onChange={(e) => setNif(e.target.value)} /></label>
        )}
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">{estFournisseur ? "Contact (facultatif)" : "Email (facultatif)"}</span>
          <input type={estFournisseur ? "text" : "email"} maxLength={200} className={CHAMP} value={detail} onChange={(e) => setDetail(e.target.value)} /></label>
        <button type="submit" disabled={enregistrerF.isPending || enregistrerA.isPending}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">
          <Plus size={16} aria-hidden /> Ajouter
        </button>
      </form>
      <ul className="bg-surface rounded-2xl border border-gray-100 divide-y divide-gray-50">
        {lignes?.length === 0 && <li className="p-4 text-sm text-muted">Aucun pour l&apos;instant.</li>}
        {lignes?.map((x) => (
          <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <span className={cn(!x.actif && "text-muted line-through")}>
              <strong>{x.nom}</strong>
              <span className="text-muted">{"nif" in x && x.nif ? ` · NIF ${x.nif}` : ""}{"contact" in x && x.contact ? ` · ${x.contact}` : ""}{"email" in x && x.email ? ` · ${x.email}` : ""}</span>
            </span>
            <ActionButton onClick={() => basculer(x.id, x.nom, x.actif)}>{x.actif ? "Désactiver" : "Réactiver"}</ActionButton>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted">{estFournisseur ? "Un fournisseur désactivé garde ses dépenses passées, mais ne se choisit plus." : "Les associés sont ceux à qui Kwa-Ba doit ce qu'ils ont avancé ; leurs comptes courants viendront avec GL-16."}</p>
    </div>
  );
}
