"use client";

import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, TriangleAlert } from "lucide-react";
import AdminTable, { Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice, isoDate } from "@/lib/utils";
import {
  urlExportTableau, urlLivreInventaire, urlRapportAssocies, urlReleveCompte, type LivreInventaire, type PartenaireAvecArgent,
  type TableauDeBord as Tableau,
} from "../api";
import {
  useCommenterRapport, useEcrireInventaire, useLivreInventaire, usePartenairesAvecArgent, useRapportAssocies,
  useReleveCompte, useTableauDeBord,
} from "../hooks";
import { BoutonTelecharger, CHAMP, ErreurLecture, libelleMois } from "./communs";

const moisCourant = () => isoDate(new Date()).slice(0, 7);
const pct = (v: number | null) => (v === null ? "—" : `${v.toLocaleString("fr-FR")} %`);

function Carte({ titre, valeur, note, ton }: { titre: string; valeur: string; note?: string; ton?: "rouge" | "vert" }) {
  return (
    <div className={cn("rounded-2xl p-4 border", ton === "rouge" ? "bg-red-50 border-red-200" : "bg-surface border-gray-100")}>
      <p className="text-xs font-semibold text-muted">{titre}</p>
      <p className={cn("font-heading font-bold text-xl tabular-nums", ton === "vert" && "text-green-700")}>{valeur}</p>
      {note && <p className="text-xs text-muted">{note}</p>}
    </div>
  );
}

function ChoixMois({ mois, onChange }: { mois: string; onChange: (m: string) => void }) {
  return (
    <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Mois</span>
      <input type="month" className={CHAMP} value={mois} max={moisCourant()} onChange={(e) => e.target.value && onChange(e.target.value)} /></label>
  );
}

/** The figures of a month, shared by the dashboard and the report to the associates. */
function Indicateurs({ t }: { t: Tableau }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Carte titre="Chiffre d'affaires" valeur={formatPrice(t.resultat.chiffre_affaires)} note={`Année : ${formatPrice(t.cumul_annee.chiffre_affaires)}`} />
        <Carte titre="Résultat du mois" valeur={formatPrice(t.resultat.resultat)} ton={t.resultat.resultat < 0 ? "rouge" : "vert"}
          note={`Année : ${formatPrice(t.cumul_annee.resultat)}`} />
        <Carte titre="Réservations payées" valeur={String(t.activite.reservations_payees)} note={`${formatPrice(t.activite.volume_encaisse)} encaissés`} />
        <Carte titre="Taux de frais réel" valeur={pct(t.activite.taux_frais_reel)} note={`${formatPrice(t.activite.frais_paiement)} de frais FedaPay`} />
      </div>
      <section className="rounded-2xl p-4 bg-surface border border-gray-100" aria-label="Trésorerie en quatre poches">
        <h2 className="font-heading font-bold text-dark mb-2">Trésorerie en quatre poches</h2>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
          {([["Argent détenu", t.poches.tresorerie], ["Dû aux partenaires et voyageurs", t.poches.du_partenaires + t.poches.du_voyageurs],
            ["Cautions", t.poches.cautions_detenues], ["Fonds de garantie", t.poches.fonds_garantie], ["Trésorerie libre", t.poches.libre]] as [string, number][]).map(([l, v]) => (
            <div key={l}><p className="text-xs text-muted">{l}</p><p className={cn("font-semibold tabular-nums", l === "Trésorerie libre" && v < 0 && "text-red-700")}>{formatPrice(v)}</p></div>
          ))}
        </div>
        <p className="text-xs text-muted mt-2">Dû aux associés (comptes courants) : {formatPrice(t.du_aux_associes)}.</p>
      </section>
      <div className="grid lg:grid-cols-2 gap-4">
        <section className="rounded-2xl p-4 bg-surface border border-gray-100" aria-label="Revenu par offre">
          <h2 className="font-heading font-bold text-dark mb-2">Revenu et marge par offre</h2>
          <ul className="text-sm divide-y divide-gray-50">
            {t.marge_par_offre.map((m) => (
              <li key={m.offre_code} className="flex justify-between gap-2 py-1.5"><span>{m.offre_code}</span>
                <span className="tabular-nums">{formatPrice(m.recettes)} · marge <strong>{formatPrice(m.marge)}</strong></span></li>
            ))}
            {t.marge_par_offre.length === 0 && <li className="py-1.5 text-muted">Aucun revenu ce mois.</li>}
          </ul>
        </section>
        <section className="rounded-2xl p-4 bg-surface border border-gray-100" aria-label="Annulations et fiscalité">
          <h2 className="font-heading font-bold text-dark mb-2">Annulations et fiscalité</h2>
          <dl className="text-sm grid grid-cols-2 gap-y-1.5">
            <dt className="text-muted">Annulations</dt><dd className="text-right tabular-nums">{t.activite.annulations} ({pct(t.activite.taux_annulation)})</dd>
            <dt className="text-muted">Remboursé aux voyageurs</dt><dd className="text-right tabular-nums">{formatPrice(t.activite.rembourse)}</dd>
            <dt className="text-muted">Frais perdus sur annulations</dt><dd className="text-right tabular-nums">{formatPrice(t.activite.frais_perdus)}</dd>
            <dt className="text-muted">Gardé après annulation (R08)</dt><dd className="text-right tabular-nums">{formatPrice(t.activite.conserve)}</dd>
            <dt className="text-muted">Impôt estimé sur l&apos;année</dt><dd className="text-right tabular-nums">{formatPrice(t.fiscal.impot_estime)}</dd>
            <dt className="text-muted">Seuil de la TVA atteint à</dt><dd className="text-right tabular-nums">{pct(t.fiscal.part_du_seuil_tva)}</dd>
          </dl>
        </section>
      </div>
      <section className="rounded-2xl p-4 bg-surface border border-gray-100" aria-label="Seuils">
        <h2 className="font-heading font-bold text-dark mb-2">Seuils des associés</h2>
        <ul className="text-sm divide-y divide-gray-50">
          {t.seuils.map((s) => (
            <li key={s.code} className="flex flex-wrap justify-between gap-2 py-2">
              <span className="flex items-center gap-2">{s.ok ? <CheckCircle2 size={14} className="text-green-700" aria-hidden /> : <TriangleAlert size={14} className="text-amber-600" aria-hidden />}{s.libelle}</span>
              <span className="tabular-nums">{formatPrice(s.valeur)} <span className="text-muted">/ {s.seuil ? formatPrice(s.seuil) : "seuil à fixer"}</span></span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted mt-2">Qualité : {t.anomalies} anomalie(s) aux invariants, {t.jours_en_ecart} journée(s) de rapprochement en écart ce mois. Seuils et scénario prudent : Finance → Paramètres.</p>
      </section>
    </div>
  );
}

/** The finance officer's dashboard (GL-18): every figure read from the ledger, exportable for the same month. */
export function TableauDeBord() {
  const [mois, setMois] = useState(moisCourant);
  const { data, isError, error, isLoading } = useTableauDeBord(`${mois}-01`);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <ChoixMois mois={mois} onChange={setMois} />
        <BoutonTelecharger url={urlExportTableau(`${mois}-01`)} nom={`tableau-de-bord-${mois}.csv`} libelle="Exporter le mois (CSV)" />
      </div>
      {isLoading && <div className="h-40 skeleton rounded-2xl" />}
      {isError && <ErreurLecture erreur={error} />}
      {data && <Indicateurs t={data} />}
    </div>
  );
}

/** Statements of the partners (GL-21): owed, paid, commissions and balance of a month, and the year. */
export function RelevesPartenaires() {
  const { data: partenaires, isError, error } = usePartenairesAvecArgent();
  const [choisi, setChoisi] = useState<PartenaireAvecArgent | null>(null);
  const [mois, setMois] = useState(moisCourant);
  const { data } = useReleveCompte(choisi?.tiers_type ?? "", choisi?.tiers_id ?? "", `${mois}-01`);
  const colonnes: Colonne<PartenaireAvecArgent>[] = [
    { titre: "Partenaire", cellule: (p) => <span className="block"><strong>{p.nom}</strong><span className="block text-xs text-muted">{p.tiers_type}</span></span>, masquerMobile: true },
    { titre: "Dernière opération", cellule: (p) => formatDate(p.derniere) },
    { titre: "Solde dû", cellule: (p) => <strong className="tabular-nums">{formatPrice(p.solde)}</strong>, className: "text-right" },
  ];
  return (
    <div className="space-y-4">
      {isError && <ErreurLecture erreur={error} />}
      <AdminTable colonnes={colonnes} lignes={partenaires} cle={(p) => `${p.tiers_type}:${p.tiers_id}`}
        titreMobile={(p) => <span className="flex justify-between gap-2">{p.nom}<span className="tabular-nums">{formatPrice(p.solde)}</span></span>}
        actions={(p) => <button onClick={() => setChoisi(p)} className="text-sm font-semibold text-brand">Relevé</button>} />
      {choisi && (
        <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label="Relevé du partenaire">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 className="font-heading font-bold text-dark">{choisi.nom} · {libelleMois(`${mois}-01`)}</h2>
            <div className="flex flex-wrap items-end gap-2">
              <ChoixMois mois={mois} onChange={setMois} />
              <BoutonTelecharger url={urlReleveCompte(choisi.tiers_type, choisi.tiers_id, `${mois}-01`)} nom={`releve-${mois}.pdf`} libelle="PDF" />
              <button onClick={() => setChoisi(null)} className="text-sm font-semibold text-brand pb-2">Fermer</button>
            </div>
          </div>
          {data && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
                {([["Solde au début", data.solde_ouverture], ["Dû sur le mois", data.du], ["Versé", data.verse], ["Commissions de Kwa-Ba", data.commissions], ["Solde à la fin", data.solde_cloture]] as [string, number][]).map(([l, v]) => (
                  <div key={l}><p className="text-xs text-muted">{l}</p><p className="font-semibold tabular-nums">{formatPrice(v)}</p></div>
                ))}
              </div>
              <ul className="text-sm divide-y divide-gray-50">
                {data.lignes.map((l) => (
                  <li key={l.id} className="flex justify-between gap-2 py-1.5"><span>{formatDate(l.date)} · {l.piece ?? "—"} · {l.nature_libelle}</span>
                    <span className="tabular-nums">{formatPrice(l.montant_signe)}</span></li>
                ))}
              </ul>
              <h3 className="font-semibold text-dark text-sm">Récapitulatif de l&apos;année</h3>
              <ul className="text-sm divide-y divide-gray-50">
                {data.recapitulatif.map((r) => (
                  <li key={r.mois} className="flex flex-wrap justify-between gap-2 py-1.5"><span className="capitalize">{libelleMois(r.mois)}</span>
                    <span className="tabular-nums text-muted">dû {formatPrice(r.du)} · versé {formatPrice(r.verse)} · solde <strong className="text-dark">{formatPrice(r.solde_cloture)}</strong></span></li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
      <p className="text-xs text-muted">Consultation : le relevé se télécharge en PDF pour être transmis au partenaire. Rien n&apos;est envoyé automatiquement.</p>
    </div>
  );
}

/** Monthly report to the associates (GL-21, pact art. 2.4): the month's figures and the referent's comment. */
export function RapportAssocies() {
  const [mois, setMois] = useState(() => {
    const d = new Date(); d.setDate(0);
    return isoDate(d).slice(0, 7);
  });
  const { data, isError, error } = useRapportAssocies(`${mois}-01`);
  const commenter = useCommenterRapport();
  const [texte, setTexte] = useState<string | null>(null);
  const valeur = texte ?? data?.commentaire?.commentaire ?? "";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <ChoixMois mois={mois} onChange={(m) => { setMois(m); setTexte(null); }} />
        <BoutonTelecharger url={urlRapportAssocies(`${mois}-01`)} nom={`rapport-associes-${mois}.pdf`} libelle="Télécharger le rapport (PDF)" principal />
      </div>
      {isError && <ErreurLecture erreur={error} />}
      <section className="bg-surface rounded-2xl border border-gray-100 p-4 space-y-2" aria-label="Commentaire du référent">
        <h2 className="font-heading font-bold text-dark">Commentaire du référent</h2>
        <textarea rows={4} maxLength={5000} className={cn(CHAMP, "w-full")} value={valeur} disabled={!data?.peut_commenter}
          onChange={(e) => setTexte(e.target.value)} placeholder="Ce qu'il faut retenir du mois, les décisions à prendre" />
        {data?.peut_commenter && (
          <button disabled={commenter.isPending || texte === null} onClick={() => commenter.mutate({ mois: `${mois}-01`, commentaire: valeur }, {
            onSuccess: () => { toast.success("Commentaire enregistré."); setTexte(null); },
            onError: (err) => toast.error(apiErrorMessage(err, "Enregistrement refusé.")),
          })} className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">Enregistrer le commentaire</button>
        )}
        {data?.commentaire?.maj_le && <p className="text-xs text-muted">Modifié le {formatDate(data.commentaire.maj_le)}.</p>}
      </section>
      {data && <Indicateurs t={data.tableau} />}
      <p className="text-xs text-muted">Consultation : le rapport se télécharge en PDF pour les sept associés, au plus tard le 10 du mois suivant. Rien n&apos;est envoyé automatiquement.</p>
    </div>
  );
}

/** Inventory of the financial year (GL-23): amortisation, inventory book, balances carried forward. */
export function Inventaire() {
  const [annee, setAnnee] = useState(new Date().getFullYear() - 1);
  const { data, isError, error } = useLivreInventaire(annee);
  const ecrire = useEcrireInventaire();
  const passer = () => ecrire.mutate(annee, {
    onSuccess: (r) => toast.success(r.ajoute ? `${formatPrice(r.ajoute)} d'amortissement écrits au 31/12/${annee}.` : "Les écritures d'inventaire sont à jour."),
    onError: (err) => toast.error(apiErrorMessage(err, "Écriture refusée.")),
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Exercice</span>
          <input type="number" className={CHAMP} value={annee} min={2026} max={new Date().getFullYear()} onChange={(e) => setAnnee(Number(e.target.value))} /></label>
        <BoutonTelecharger url={urlLivreInventaire(annee)} nom={`livre-inventaire-${annee}.csv`} libelle="Exporter le livre (CSV)" />
        {data?.peut_ecrire && <button onClick={passer} disabled={ecrire.isPending} className="px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60">Passer les écritures d&apos;inventaire</button>}
      </div>
      {isError && <ErreurLecture erreur={error} />}
      {data && <LivreInventaireVue livre={data} />}
    </div>
  );
}

function LivreInventaireVue({ livre }: { livre: LivreInventaire }) {
  const a = livre.amortissement;
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-3 gap-3">
        <Carte titre="Résultat de l'exercice" valeur={formatPrice(livre.compte_de_resultat.resultat)} ton={livre.compte_de_resultat.resultat < 0 ? "rouge" : "vert"}
          note={`Produits ${formatPrice(livre.compte_de_resultat.produits)} · charges ${formatPrice(livre.compte_de_resultat.charges)}`} />
        <Carte titre="Bilan" valeur={formatPrice(livre.bilan.total_actif)} note={`Passif ${formatPrice(livre.bilan.total_passif)} · ${livre.equilibre ? "balance équilibrée" : "balance déséquilibrée"}`} ton={livre.equilibre ? undefined : "rouge"} />
        <Carte titre="Amortissement de la Solution" valeur={formatPrice(a.du)}
          note={a.valeur ? `${a.mois} mois sur ${a.duree_mois}, écrit ${formatPrice(a.ecrit)}` : "Valeur et durée à fixer (Finance → Paramètres)"} />
      </div>
      <section className="bg-surface rounded-2xl border border-gray-100 p-4" aria-label="Écritures d'inventaire">
        <h2 className="font-heading font-bold text-dark mb-2">Écritures d&apos;inventaire</h2>
        <ul className="text-sm divide-y divide-gray-50">
          {livre.ecritures.map((e) => (
            <li key={e.id} className="flex flex-wrap justify-between gap-2 py-1.5"><span>{formatDate(e.date)} · {e.piece} · {e.nature_libelle} <span className="text-muted">({e.compte} / {e.contrepartie})</span></span>
              <span className="tabular-nums">{formatPrice(Math.abs(e.montant_signe))}</span></li>
          ))}
          {livre.ecritures.length === 0 && <li className="py-1.5 text-muted">Aucune pour cet exercice.</li>}
        </ul>
      </section>
      <section className="bg-surface rounded-2xl border border-gray-100 p-4" aria-label="À-nouveaux">
        <h2 className="font-heading font-bold text-dark mb-2">À-nouveaux au 1er janvier {livre.annee + 1}</h2>
        <ul className="text-sm divide-y divide-gray-50">
          {livre.a_nouveaux.map((n) => (
            <li key={n.compte_general} className="flex justify-between gap-2 py-1.5"><span><strong>{n.compte_general}</strong> {n.libelle}</span>
              <span className="tabular-nums">{formatPrice(Math.abs(n.solde))} <Pill ton="gris">{n.solde > 0 ? "D" : "C"}</Pill></span></li>
          ))}
        </ul>
        <p className="text-xs text-muted mt-2">Les comptes de bilan reprennent leur solde ; le résultat attend son affectation par l&apos;assemblée des associés (131 bénéfice, 139 perte).</p>
      </section>
    </div>
  );
}
