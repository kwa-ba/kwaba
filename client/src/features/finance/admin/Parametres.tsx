"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import type { ChangementParametre, ParametreFinance } from "../api";
import { useHistoriqueParametre, useModifierParametre, useParametres } from "../hooks";
import { CHAMP, ErreurLecture } from "./communs";

const CATEGORIES: [string, string][] = [["", "Toutes"], ["tarif", "Taux"], ["forfait", "Forfaits"], ["plafond", "Plafonds"],
  ["delai", "Délais"], ["seuil", "Seuils"], ["interne", "Internes"]];
const UNITES: Record<string, string> = { pourcentage: "%", fcfa: "F CFA", heures: "h", jours: "jours", nuits: "nuits", mois: "mois", code: "" };
const nombre = (v: string | number | null) => (v === null ? "—" : Number(v).toLocaleString("fr-FR"));

/**
 * Steered parameters (GL-20): every rate, fixed fee, cap, delay and threshold the team decides, with its source and its
 * dated history (who, when, before and after, why). A super administrator changes a value with its reason; the rates
 * the site reads at every booking change on the Tarifs page. A value at zero leaves its rule inert.
 */
export default function Parametres() {
  const { data, isLoading, isError, error } = useParametres();
  const [categorie, setCategorie] = useState("");
  const [recherche, setRecherche] = useState("");
  const [actifs, setActifs] = useState(true);
  const [choisi, setChoisi] = useState<ParametreFinance | null>(null);

  const lignes = useMemo(() => (data?.parametres ?? []).filter((p) =>
    (!categorie || p.categorie === categorie) && (!actifs || p.actif)
    && (!recherche || `${p.cle} ${p.libelle} ${p.offre ?? ""}`.toLowerCase().includes(recherche.toLowerCase()))), [data, categorie, recherche, actifs]);

  const colonnes: Colonne<ParametreFinance>[] = [
    { titre: "Paramètre", cellule: (p) => (
      <span className="block min-w-0"><strong className={cn(!p.actif && "text-muted")}>{p.libelle}</strong>
        <span className="block text-xs text-muted">{p.cle}{p.offre ? ` · ${p.offre}` : ""}{p.source ? ` · ${p.source}` : ""}</span></span>
    ), masquerMobile: true },
    { titre: "État", cellule: (p) => (
      <span className="flex flex-wrap gap-1">
        {!p.actif && <Pill ton="gris">Offre non ouverte</Pill>}
        {p.actif && Number(p.valeur) === 0 && <Pill ton="orange">À fixer</Pill>}
        {p.page_tarifs && <Pill ton="bleu">Page Tarifs</Pill>}
      </span>
    ) },
    { titre: "Valeur", cellule: (p) => <strong className="tabular-nums whitespace-nowrap">{nombre(p.valeur)} {UNITES[p.unite] ?? p.unite}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-3">
        <label className="text-sm min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Rechercher</span>
          <input className={CHAMP} value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="commission, caution, délai…" /></label>
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Catégorie</span>
          <select className={CHAMP} value={categorie} onChange={(e) => setCategorie(e.target.value)}>
            {CATEGORIES.map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
          </select></label>
        <label className="text-sm flex items-center gap-2 pb-2">
          <input type="checkbox" checked={actifs} onChange={(e) => setActifs(e.target.checked)} /> Offres ouvertes seulement
        </label>
      </div>
      {isError && <ErreurLecture erreur={error} />}
      {data && !data.peut_modifier && (
        <p className="text-sm bg-amber-50 text-amber-900 rounded-xl px-4 py-3">Consultation seulement : un paramètre est modifié par un super administrateur.</p>
      )}
      <AdminTable colonnes={colonnes} lignes={data ? lignes : undefined} cle={(p) => p.cle} chargement={isLoading}
        titreMobile={(p) => <span className="flex justify-between gap-2">{p.libelle}<span className="tabular-nums">{nombre(p.valeur)} {UNITES[p.unite] ?? ""}</span></span>}
        actions={(p) => <ActionButton onClick={() => setChoisi(p)}>{data?.peut_modifier && !p.page_tarifs ? "Modifier" : "Historique"}</ActionButton>} />
      {data && lignes.length === 0 && <p className="text-sm text-muted">Aucun paramètre pour ces filtres.</p>}
      {choisi && <Detail parametre={choisi} peutModifier={!!data?.peut_modifier && !choisi.page_tarifs} onFermer={() => setChoisi(null)} />}
      {data && <Derniers historique={data.historique} />}
    </div>
  );
}

function Historique({ lignes }: { lignes: ChangementParametre[] }) {
  if (!lignes.length) return <p className="text-sm text-muted">Jamais modifié depuis sa création.</p>;
  return (
    <ul className="text-sm divide-y divide-gray-100">
      {lignes.map((h, i) => (
        <li key={`${h.cle}-${h.date_effet}-${i}`} className="flex flex-wrap justify-between gap-2 py-2">
          <span className="min-w-0"><strong>{formatDate(h.date_effet)}</strong>{h.par && ` · ${h.par}`}
            {h.motif && <span className="block text-xs text-muted">{h.motif}</span>}</span>
          <span className="tabular-nums whitespace-nowrap">{nombre(h.valeur_avant)} → {nombre(h.valeur_apres)}</span>
        </li>
      ))}
    </ul>
  );
}

function Detail({ parametre, peutModifier, onFermer }: { parametre: ParametreFinance; peutModifier: boolean; onFermer: () => void }) {
  const { data } = useHistoriqueParametre(parametre.cle);
  const modifier = useModifierParametre();
  const [valeur, setValeur] = useState(String(Number(parametre.valeur)));
  const [motif, setMotif] = useState("");
  const envoyer = (e: React.FormEvent) => {
    e.preventDefault();
    modifier.mutate({ cle: parametre.cle, valeur, motif }, {
      onSuccess: () => { toast.success(`${parametre.libelle} : nouvelle valeur enregistrée.`); onFermer(); },
      onError: (err) => toast.error(apiErrorMessage(err, "Modification refusée.")),
    });
  };
  return (
    <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label={`Paramètre ${parametre.cle}`}>
      <div className="flex justify-between gap-2">
        <h2 className="font-heading font-bold text-dark">{parametre.libelle}</h2>
        <button onClick={onFermer} className="text-sm font-semibold text-brand">Fermer</button>
      </div>
      {parametre.page_tarifs && <p className="text-xs text-muted">Ce taux se modifie dans la page Tarifs : le site le lit à chaque réservation.</p>}
      {peutModifier && (
        <form onSubmit={envoyer} className="grid sm:grid-cols-3 gap-3 items-end">
          <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Nouvelle valeur ({UNITES[parametre.unite] || parametre.unite})</span>
            <input required inputMode="decimal" className={cn(CHAMP, "w-full")} value={valeur} onChange={(e) => setValeur(e.target.value)} /></label>
          <label className="text-sm sm:col-span-2 min-w-0"><span className="block text-xs font-semibold text-muted mb-1">Pourquoi (décision, document)</span>
            <input required minLength={10} maxLength={500} className={cn(CHAMP, "w-full")} value={motif} onChange={(e) => setMotif(e.target.value)}
              placeholder="Ex. : décision des associés du 19 novembre 2026" /></label>
          <button type="submit" disabled={modifier.isPending} className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60 sm:col-span-3 sm:justify-self-start">
            {modifier.isPending ? "Envoi…" : "Enregistrer la nouvelle valeur"}
          </button>
        </form>
      )}
      <Historique lignes={data?.historique ?? []} />
    </section>
  );
}

function Derniers({ historique }: { historique: ChangementParametre[] }) {
  return (
    <section className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-2" aria-label="Derniers changements">
      <h2 className="font-heading font-bold text-dark">Derniers changements</h2>
      <ul className="text-sm divide-y divide-gray-100">
        {historique.map((h, i) => (
          <li key={`${h.cle}-${h.date_effet}-${i}`} className="flex flex-wrap justify-between gap-2 py-2">
            <span className="min-w-0"><strong>{h.cle}</strong> <span className="text-muted">· {formatDate(h.date_effet)}{h.par && ` · ${h.par}`}</span>
              {h.motif && <span className="block text-xs text-muted">{h.motif}</span>}</span>
            <span className="tabular-nums whitespace-nowrap">{nombre(h.valeur_avant)} → {nombre(h.valeur_apres)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
