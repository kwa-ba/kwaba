"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import Panneau, { Champ, Interrupteur, Saisie, erreursApi } from "@/components/backoffice/Panneau";
import { creerGamme, modifierGamme } from "../api";
import { clesMobilite, useGammesAdmin } from "../hooks";
import type { GammeAdmin } from "../types";

type Formulaire = Omit<GammeAdmin, "places" | "bagages" | "ordre"> & { places: string; bagages: string; ordre: string };
const VIDE: Formulaire = {
  code: "", libelle: "", libelle_en: "", description: "", description_en: "", places: "4", bagages: "2",
  propose_transfert: false, propose_location: true, ordre: "0", actif: true,
};

/** The single referential of vehicle ranges (T-H1): the same word for a transfer and a rental. A range offered in
 * transfer gets a fare per airport (Transferts → Aéroports et tarifs). */
export default function Gammes() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useGammesAdmin();
  const [edition, setEdition] = useState<GammeAdmin | "nouvelle" | null>(null);
  const [form, setForm] = useState<Formulaire>(VIDE);
  const [erreurs, setErreurs] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);

  const ouvrir = (g: GammeAdmin | "nouvelle") => {
    setEdition(g);
    setForm(g === "nouvelle" ? VIDE : { ...g, places: String(g.places), bagages: String(g.bagages), ordre: String(g.ordre) });
    setErreurs({});
  };

  const enregistrer = async () => {
    setEnvoi(true);
    setErreurs({});
    const corps = { ...form, places: Number(form.places), bagages: Number(form.bagages), ordre: Number(form.ordre) };
    try {
      if (edition === "nouvelle") await creerGamme(corps);
      else if (edition) await modifierGamme(edition.code, corps);
      toast.success("Gamme enregistrée");
      setEdition(null);
      queryClient.invalidateQueries({ queryKey: clesMobilite.admin });
      queryClient.invalidateQueries({ queryKey: clesMobilite.tous });
    } catch (err) {
      setErreurs(erreursApi(err));
    } finally {
      setEnvoi(false);
    }
  };

  const colonnes: Colonne<GammeAdmin>[] = [
    { titre: "Gamme", masquerMobile: true, cellule: (g) => <div><p className="font-semibold text-dark">{g.libelle} <span className="text-muted font-mono text-xs">{g.code}</span></p><p className="text-xs text-muted">{g.description}</p></div> },
    { titre: "Transfert", cellule: (g) => <span className="text-xs">{g.propose_transfert ? `${g.places} passagers, ${g.bagages} valises` : "—"}</span> },
    { titre: "Proposée en", cellule: (g) => <span className="flex gap-1">{g.propose_transfert && <Pill ton="bleu">Transfert</Pill>}{g.propose_location && <Pill ton="vert">Location</Pill>}</span> },
    { titre: "Statut", cellule: (g) => <Pill ton={g.actif ? "vert" : "gris"}>{g.actif ? "Active" : "Désactivée"}</Pill> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center gap-3">
        <p className="text-sm text-muted">Un seul mot par gamme, en transfert comme en location. La boîte automatique est un attribut du véhicule, pas une gamme.</p>
        <button onClick={() => ouvrir("nouvelle")} className="shrink-0 px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-bold">Nouvelle gamme</button>
      </div>
      <AdminTable colonnes={colonnes} lignes={data} cle={(g) => g.code} titreMobile={(g) => colonnes[0].cellule(g)}
        actions={(g) => <ActionButton onClick={() => ouvrir(g)}>Modifier</ActionButton>}
        chargement={isLoading} erreur={isError} onReessayer={refetch} />

      <Panneau ouvert={!!edition} titre={edition === "nouvelle" ? "Nouvelle gamme" : "Modifier la gamme"} onFermer={() => setEdition(null)} onValider={enregistrer} envoi={envoi}>
        {erreurs.detail && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurs.detail}</p>}
        <Champ label="Code" aide="Gardé par les réservations et les véhicules : il ne change plus" erreur={erreurs.code}>
          <Saisie value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toLowerCase() })} required disabled={edition !== "nouvelle"} placeholder="berline" maxLength={20} />
        </Champ>
        <div className="grid grid-cols-2 gap-3">
          <Champ label="Nom" erreur={erreurs.libelle}><Saisie value={form.libelle} onChange={(e) => setForm({ ...form, libelle: e.target.value })} required /></Champ>
          <Champ label="Nom en anglais" erreur={erreurs.libelle_en}><Saisie value={form.libelle_en} onChange={(e) => setForm({ ...form, libelle_en: e.target.value })} required /></Champ>
          <Champ label="Description" erreur={erreurs.description}><Saisie value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Toyota Corolla ou similaire" /></Champ>
          <Champ label="Description en anglais" erreur={erreurs.description_en}><Saisie value={form.description_en} onChange={(e) => setForm({ ...form, description_en: e.target.value })} /></Champ>
          <Champ label="Passagers (transfert)" erreur={erreurs.places}><Saisie type="number" min={1} value={form.places} onChange={(e) => setForm({ ...form, places: e.target.value })} required /></Champ>
          <Champ label="Valises (transfert)" erreur={erreurs.bagages}><Saisie type="number" min={0} value={form.bagages} onChange={(e) => setForm({ ...form, bagages: e.target.value })} required /></Champ>
          <Champ label="Ordre d'affichage" erreur={erreurs.ordre}><Saisie type="number" min={0} value={form.ordre} onChange={(e) => setForm({ ...form, ordre: e.target.value })} /></Champ>
        </div>
        <Interrupteur label="Proposée en transfert aéroport (avec un tarif par aéroport)" checked={form.propose_transfert} onChange={(v) => setForm({ ...form, propose_transfert: v })} />
        <Interrupteur label="Proposée en location" checked={form.propose_location} onChange={(v) => setForm({ ...form, propose_location: v })} />
        <Interrupteur label="Active" checked={form.actif} onChange={(v) => setForm({ ...form, actif: v })} />
      </Panneau>
    </div>
  );
}
