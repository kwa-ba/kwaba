"use client";

import { enregistrerRegles, lireRegles, lireTarifsMobilite, type TarifMobilite } from "../api";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Champ, Interrupteur, Saisie, Zone, erreursApi } from "@/components/backoffice/Panneau";

// The commission is no longer entered here: it is the parameter `commission_vehicule` of Finance → Paramètres (T-H10)
const VIDE = {
  delai_min_jours: "2", duree_max_jours: "30", annulation_gratuite_heures: "48", conditions: "",
  caution_en_ligne: true, restitution_caution_heures: "24",
};
const OFFRES: Record<TarifMobilite["offre"], string> = {
  VOITURE_CH: "Voiture avec chauffeur et chauffeurs", VOITURE_SANS: "Voiture sans chauffeur", TRANSFERT: "Transferts aéroport",
};

function valeurLisible(t: TarifMobilite) {
  const n = Number(t.valeur);
  const nombre = n.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
  if (t.unite === "pourcentage") return `${nombre} %`;
  if (t.unite === "fcfa") return `${nombre} FCFA`;
  if (t.unite === "code") return nombre;
  return `${nombre} ${t.unite}`;
}

/** The rates and rules of the mobility offers, read only: one place to change them, Finance → Paramètres. */
export function TarifsMobilite() {
  const { data: tarifs = [] } = useQuery({ queryKey: ["admin", "location", "tarifs-mobilite"], queryFn: lireTarifsMobilite });
  if (!tarifs.length) return null;
  return (
    <section className="bg-surface rounded-2xl border border-gray-100 p-5 sm:p-6 space-y-3 max-w-2xl" aria-label="Tarifs et règles mobilité">
      <div className="flex justify-between items-baseline gap-3">
        <h2 className="font-heading font-bold text-dark">Tarifs &amp; règles mobilité</h2>
        <Link href="/backoffice/finances/parametres" className="text-sm font-semibold text-brand shrink-0">Modifier dans Finance → Paramètres</Link>
      </div>
      <p className="text-xs text-muted">Une seule source : ces valeurs se changent dans Finance → Paramètres (la commission des transferts sur la page Tarifs) et s&apos;appliquent partout, location comme transferts.</p>
      {(Object.keys(OFFRES) as TarifMobilite["offre"][]).map((offre) => {
        const lignes = tarifs.filter((t) => t.offre === offre);
        if (!lignes.length) return null;
        return (
          <div key={offre}>
            <h3 className="text-xs font-bold text-dark uppercase tracking-wide mb-1">{OFFRES[offre]}</h3>
            <dl className="divide-y divide-gray-50 text-sm">
              {lignes.map((t) => (
                <div key={t.cle} className="flex justify-between gap-3 py-1.5">
                  <dt className="text-gray-600">{t.libelle}</dt>
                  <dd className="font-semibold tabular-nums shrink-0">{valeurLisible(t)}</dd>
                </div>
              ))}
            </dl>
          </div>
        );
      })}
    </section>
  );
}

/** Rental rules: as long as they are not saved, rental is not offered on the site. */
export default function Regles() {
  const queryClient = useQueryClient();
  const { data: regles, isLoading } = useQuery({
    queryKey: ["admin", "location", "regles"],
    queryFn: lireRegles,
  });
  const [form, setForm] = useState(VIDE);
  const [erreurs, setErreurs] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    if (regles) setForm({ conditions: regles.conditions, caution_en_ligne: regles.caution_en_ligne,
      delai_min_jours: String(regles.delai_min_jours), duree_max_jours: String(regles.duree_max_jours),
      annulation_gratuite_heures: String(regles.annulation_gratuite_heures), restitution_caution_heures: String(regles.restitution_caution_heures) });
  }, [regles]);

  const enregistrer = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnvoi(true);
    setErreurs({});
    try {
      await enregistrerRegles(form);
      toast.success("Règles enregistrées");
      queryClient.invalidateQueries({ queryKey: ["admin", "location", "regles"] });
    } catch (err) {
      setErreurs(erreursApi(err));
    } finally {
      setEnvoi(false);
    }
  };

  if (isLoading) return <div className="h-64 skeleton rounded-2xl" />;
  return (
    <div className="space-y-5">
    <form method="post" onSubmit={enregistrer} className="bg-surface rounded-2xl border border-gray-100 p-5 sm:p-6 space-y-4 max-w-2xl">
      {!regles && <p className="text-sm bg-amber-50 text-amber-900 rounded-xl p-3">La location n&apos;est pas encore proposée sur le site : enregistrez ces règles pour l&apos;ouvrir.</p>}
      {erreurs.detail && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurs.detail}</p>}
      {regles && (
        <p className="text-sm text-gray-700">
          Commission sur le véhicule : <strong>{regles.commission_pourcent.toLocaleString("fr-FR")} %</strong> (10 % pour un fondateur, 12 % après 20 locations sans incident),
          réglée dans <Link href="/backoffice/finances/parametres" className="font-semibold text-brand">Finance → Paramètres</Link>.
        </p>
      )}
      <div className="grid sm:grid-cols-2 gap-4">
        <Champ label="Réservation au plus tard (jours avant)" aide="Temps de préparation du propriétaire et du chauffeur" erreur={erreurs.delai_min_jours}>
          <Saisie type="number" min={1} value={form.delai_min_jours} onChange={(e) => setForm({ ...form, delai_min_jours: e.target.value })} required />
        </Champ>
        <Champ label="Durée maximale (jours)" erreur={erreurs.duree_max_jours}>
          <Saisie type="number" min={1} value={form.duree_max_jours} onChange={(e) => setForm({ ...form, duree_max_jours: e.target.value })} required />
        </Champ>
        <Champ label="Annulation gratuite (heures avant)" aide="Intégral au-delà (48) ; 50 % jusqu'à 24 h avant ; rien ensuite" erreur={erreurs.annulation_gratuite_heures}>
          <Saisie type="number" min={0} value={form.annulation_gratuite_heures} onChange={(e) => setForm({ ...form, annulation_gratuite_heures: e.target.value })} required />
        </Champ>
      </div>
      <div className="rounded-xl border border-gray-100 p-4 space-y-3">
        <Interrupteur label="Caution payée en ligne et gardée par Kwa-Ba" checked={form.caution_en_ligne}
          onChange={(v) => setForm({ ...form, caution_en_ligne: v })} />
        <p className="text-xs text-muted">
          {form.caution_en_ligne
            ? "Le voyageur paie la caution avec la location et ne règle rien au propriétaire. Après le retour, le propriétaire signale les dommages à Kwa-Ba ; la retenue (Suivi des locations) lui est versée, le reste est remboursé au voyageur."
            : "Le voyageur règle la caution au propriétaire à la remise du véhicule : Kwa-Ba n'en a pas le contrôle."}
        </p>
        {form.caution_en_ligne && (
          <Champ label="Signalement des dommages (heures après le retour)" aide="Ensuite, la caution moins la retenue est remboursée au voyageur et le propriétaire payé"
            erreur={erreurs.restitution_caution_heures}>
            <Saisie type="number" min={1} value={form.restitution_caution_heures} onChange={(e) => setForm({ ...form, restitution_caution_heures: e.target.value })} required />
          </Champ>
        )}
      </div>
      <Champ label="Conditions affichées au voyageur" aide="Âge minimum, permis, carburant, kilométrage…" erreur={erreurs.conditions}>
        <Zone rows={4} value={form.conditions} onChange={(e) => setForm({ ...form, conditions: e.target.value })} />
      </Champ>
      <div className="flex justify-end">
        <button type="submit" disabled={envoi} className="px-6 py-2.5 rounded-xl bg-primary text-white text-sm font-bold disabled:opacity-50">{envoi ? "Enregistrement…" : "Enregistrer"}</button>
      </div>
    </form>
    <p className="text-xs text-muted max-w-2xl">Les autres tarifs de la mobilité (chauffeurs, transferts, cautions) sont regroupés dans Mobilité → Tarifs &amp; règles.</p>
    </div>
  );
}
