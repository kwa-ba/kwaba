"use client";

import {
  creerChauffeur, envoyerPhotoChauffeur, lireRevueNiveaux, lireSuiviChauffeur, modifierChauffeur, signalerIncident, validerNiveau,
  validerPhotoChauffeur, type LigneRevueNiveaux, type TypeIncident,
} from "../api";
import { clesTransferts, useAeroportsAdmin, useChauffeurs } from "../hooks";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useConfigPaiement } from "@/features/paiements";
import AdminTable, { ActionButton, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import Panneau, { Champ, Interrupteur, LIBELLE_ADMIN, Liste, Saisie, erreursApi } from "@/components/backoffice/Panneau";
import PhoneInput, { useErreurTelephone } from "@/components/ui/PhoneInput";
import { PAYS_PAR_DEFAUT } from "@/lib/telephone/countries";
import { composerTelephone, decomposerTelephone, estCodePays } from "@/lib/telephone/telephone";
import { CATEGORIES_TRANSFERT } from "./Aeroports";
import type { ChauffeurAdmin } from "@/types/api/admin";

type Formulaire = Omit<ChauffeurAdmin, "id" | "nb_transferts" | "niveau" | "niveau_libelle" | "niveau_depuis" | "photo" | "photo_validee">;
// Levels of the project book (charter B6): Standard and Excellence
const NIVEAUX: Record<"standard" | "excellence", { libelle: string; ton: "gris" | "vert" }> = {
  standard: { libelle: "Standard", ton: "gris" }, excellence: { libelle: "Excellence", ton: "vert" },
};
// The history may hold the intermediate level removed on 26 November 2026
const libelleHistorique = (n: string) => NIVEAUX[n as keyof typeof NIVEAUX]?.libelle ?? "Ancien niveau intermédiaire (retiré)";
const INCIDENTS: Record<TypeIncident, string> = {
  retard: "Retard de plus de 15 min", absence: "Absence", plainte: "Plainte fondée", accident: "Accident responsable",
  grave: "Incident grave", autre: "Autre",
};
const VIDE: Formulaire = { prenom: "", nom: "", telephone: "", email: "", aeroports: [], categorie: "berline", vehicule: "", immatriculation: "",
  actif: true, excellence: false, fondateur_debut: null, fondateur_fin: null, pays_versement: "TG", operateur_versement: "", numero_versement: "" };

export default function Chauffeurs() {
  const queryClient = useQueryClient();
  const { data: config } = useConfigPaiement();
  const { data, isLoading, isError, refetch } = useChauffeurs();
  const { data: aeroports = [] } = useAeroportsAdmin();
  const [edition, setEdition] = useState<ChauffeurAdmin | "nouveau" | null>(null);
  const [form, setForm] = useState<Formulaire>(VIDE);
  const [erreurs, setErreurs] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);
  const erreurTelephone = useErreurTelephone();
  const paysVersement = estCodePays(form.pays_versement) ? form.pays_versement : PAYS_PAR_DEFAUT;
  const pays = config?.pays ?? [];
  const operateurs = pays.find((p) => p.code === form.pays_versement)?.operateurs ?? [];

  const ouvrir = (c: ChauffeurAdmin | "nouveau") => {
    setEdition(c);
    if (c === "nouveau") setForm(VIDE);
    else {
      const { prenom, nom, telephone, email, aeroports, categorie, vehicule, immatriculation, actif, excellence, pays_versement,
        operateur_versement, numero_versement, fondateur_debut = null, fondateur_fin = null } = c;
      setForm({ prenom, nom, telephone, email, aeroports, categorie, vehicule, immatriculation, actif, excellence, pays_versement,
        operateur_versement, numero_versement, fondateur_debut, fondateur_fin });
    }
    setErreurs({});
  };

  const enregistrer = async () => {
    const invalide = erreurTelephone(form.telephone);
    const versementInvalide = erreurTelephone(composerTelephone(form.pays_versement, form.numero_versement), paysVersement);
    if (invalide || versementInvalide) {
      setErreurs({ ...(invalide && { telephone: invalide }), ...(versementInvalide && { numero_versement: versementInvalide }) });
      return;
    }
    setEnvoi(true);
    try {
      if (edition === "nouveau") await creerChauffeur(form);
      else if (edition) await modifierChauffeur(edition.id, form);
      toast.success("Chauffeur enregistré");
      setEdition(null);
      queryClient.invalidateQueries({ queryKey: clesTransferts.admin });
    } catch (err) {
      setErreurs(erreursApi(err));
    } finally {
      setEnvoi(false);
    }
  };

  const nomCategorie = (c: string) => CATEGORIES_TRANSFERT.find((x) => x.code === c)?.nom ?? c;
  const colonnes: Colonne<ChauffeurAdmin>[] = [
    { titre: "Chauffeur", masquerMobile: true, cellule: (c) => <div><p className="font-semibold text-dark">{c.prenom} {c.nom}</p><p className="text-xs text-muted">{c.telephone}</p></div> },
    { titre: "Véhicule", cellule: (c) => <span className="text-xs">{nomCategorie(c.categorie)} · {c.vehicule} · {c.immatriculation}</span> },
    { titre: "Aéroports", cellule: (c) => <span className="text-xs">{c.aeroports.join(", ") || "-"}</span> },
    { titre: "Courses", cellule: (c) => <span className="tabular-nums">{c.nb_transferts}</span> },
    { titre: "Niveau", cellule: (c) => <Pill ton={NIVEAUX[c.niveau ?? "standard"].ton}>{NIVEAUX[c.niveau ?? "standard"].libelle}</Pill> },
    { titre: "Photo", cellule: (c) => c.photo_validee ? <Pill ton="vert">Validée</Pill>
      : <Pill ton={c.photo ? "orange" : "rouge"}>{c.photo ? "À valider" : "Manquante"}</Pill> },
    { titre: "Statut", cellule: (c) => <Pill ton={c.actif ? "vert" : "gris"}>{c.actif ? "Actif" : "Désactivé"}</Pill> },
  ];
  const [suivi, setSuivi] = useState<ChauffeurAdmin | null>(null);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center gap-3">
        <p className="text-sm text-muted">Chauffeurs partenaires, payés par Mobile Money après chaque course (moins la commission).</p>
        <button onClick={() => ouvrir("nouveau")} className="shrink-0 px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-bold">Nouveau chauffeur</button>
      </div>
      <AdminTable colonnes={colonnes} lignes={data} cle={(c) => String(c.id)} titreMobile={(c) => colonnes[0].cellule(c)}
        actions={(c) => <><ActionButton onClick={() => ouvrir(c)}>Modifier</ActionButton><ActionButton onClick={() => setSuivi(c)}>Suivi</ActionButton></>}
        chargement={isLoading} erreur={isError} onReessayer={refetch} />
      <p className="text-xs text-muted">Sans photo validée par l&apos;équipe, un chauffeur ne reçoit aucune course ni mission. Le voyageur voit la photo et le niveau une fois le chauffeur attribué.</p>
      {suivi && <Suivi chauffeur={suivi} onFermer={() => setSuivi(null)} />}
      <RevueNiveaux />

      <Panneau ouvert={!!edition} titre={edition === "nouveau" ? "Nouveau chauffeur" : "Modifier le chauffeur"} onFermer={() => setEdition(null)} onValider={enregistrer} envoi={envoi}>
        {erreurs.detail && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurs.detail}</p>}
        <div className="grid grid-cols-2 gap-3">
          <Champ label="Prénom" erreur={erreurs.prenom}><Saisie value={form.prenom} onChange={(e) => setForm({ ...form, prenom: e.target.value })} required /></Champ>
          <Champ label="Nom" erreur={erreurs.nom}><Saisie value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required /></Champ>
          <PhoneInput label="Téléphone" labelClassName={LIBELLE_ADMIN} taille="compact" autoComplete="off" required
            value={form.telephone} onChange={(telephone) => setForm({ ...form, telephone })} error={erreurs.telephone} />
          <Champ label="Email (facultatif)" erreur={erreurs.email}><Saisie type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Champ>
        </div>
        <fieldset>
          <legend className="block text-xs font-bold text-dark uppercase tracking-wide mb-1.5">Aéroports desservis</legend>
          <div className="flex flex-wrap gap-2">
            {aeroports.map((a) => {
              const actif = form.aeroports.includes(a.code);
              return (
                <button key={a.code} type="button" aria-pressed={actif}
                  onClick={() => setForm({ ...form, aeroports: actif ? form.aeroports.filter((x) => x !== a.code) : [...form.aeroports, a.code] })}
                  className={cn("relative zone-tactile px-3 py-1.5 rounded-full text-sm border", actif ? "bg-primary text-white border-primary" : "bg-surface text-dark border-gray-200")}>
                  {a.ville} ({a.code})
                </button>
              );
            })}
          </div>
          {erreurs.aeroports && <p role="alert" className="text-xs text-red-600 mt-1">{erreurs.aeroports}</p>}
        </fieldset>
        <div className="grid grid-cols-2 gap-3">
          <Champ label="Catégorie"><Liste value={form.categorie} onChange={(e) => setForm({ ...form, categorie: e.target.value as Formulaire["categorie"] })}
            options={CATEGORIES_TRANSFERT.map((c) => ({ value: c.code, label: c.nom }))} /></Champ>
          <Champ label="Immatriculation" erreur={erreurs.immatriculation}><Saisie value={form.immatriculation} onChange={(e) => setForm({ ...form, immatriculation: e.target.value })} required /></Champ>
        </div>
        <Champ label="Véhicule (marque, modèle, couleur)" erreur={erreurs.vehicule}><Saisie value={form.vehicule} onChange={(e) => setForm({ ...form, vehicule: e.target.value })} required placeholder="Toyota Corolla grise" /></Champ>
        <p className="text-xs font-bold text-dark uppercase tracking-wide pt-2">Versement Mobile Money</p>
        <div className="grid grid-cols-2 gap-3">
          <PhoneInput label="Numéro" labelClassName={LIBELLE_ADMIN} taille="compact" autoComplete="off" required
            value={composerTelephone(form.pays_versement, form.numero_versement)}
            onChange={(v) => setForm((f) => ({ ...f, numero_versement: decomposerTelephone(v, paysVersement).numero }))}
            paysParDefaut={paysVersement} paysAutorises={pays.map((p) => p.code).filter(estCodePays)}
            onPaysChange={(iso) => setForm((f) => ({ ...f, pays_versement: iso, operateur_versement: "" }))}
            error={erreurs.numero_versement || erreurs.pays_versement} />
          <Champ label="Opérateur" erreur={erreurs.operateur_versement}><Liste value={form.operateur_versement} required
            onChange={(e) => setForm({ ...form, operateur_versement: e.target.value })}
            options={[{ value: "", label: "Choisir" }, ...operateurs.map((o) => ({ value: o.code, label: o.nom }))]} /></Champ>
        </div>
        <p className="text-xs font-bold text-dark uppercase tracking-wide pt-2">Programme Fondateurs</p>
        <div className="grid grid-cols-2 gap-3">
          <Champ label="Premier jour" erreur={erreurs.fondateur_debut}><Saisie type="date" value={form.fondateur_debut ?? ""}
            onChange={(e) => setForm({ ...form, fondateur_debut: e.target.value || null })} /></Champ>
          <Champ label="Dernier jour (6 mois)" erreur={erreurs.fondateur_fin}><Saisie type="date" value={form.fondateur_fin ?? ""}
            onChange={(e) => setForm({ ...form, fondateur_fin: e.target.value || null })} /></Champ>
        </div>
        <p className="text-xs text-muted">Les 10 premiers chauffeurs, pendant 6 mois : niveau Excellence dès 10 missions au lieu de 20. Laissez vide hors programme.</p>
        <Interrupteur label="Actif (reçoit des courses et des missions)" checked={form.actif} onChange={(v) => setForm({ ...form, actif: v })} />
        {edition && edition !== "nouveau" && <Photo chauffeur={edition} onChange={() => queryClient.invalidateQueries({ queryKey: clesTransferts.admin })} />}
        {edition === "nouveau" && <p className="text-xs text-muted">Enregistrez le chauffeur, puis ajoutez sa photo de profil : il ne reçoit aucune course sans photo validée.</p>}
        <p className="text-xs text-muted">Niveau : il se fixe dans la revue trimestrielle ci-dessous (Excellence : 6 500 FCFA par jour au lieu de 6 000). Un incident grave retire l&apos;Excellence immédiatement.</p>
      </Panneau>
    </div>
  );
}

/** The profile photo: uploaded, then validated by the team (a clear face, the driver's own). */
function Photo({ chauffeur, onChange }: { chauffeur: ChauffeurAdmin; onChange: () => void }) {
  const [photo, setPhoto] = useState(chauffeur.photo ?? null);
  const [validee, setValidee] = useState(!!chauffeur.photo_validee);
  const [envoi, setEnvoi] = useState(false);
  const agir = async (action: () => Promise<ChauffeurAdmin>, message: string) => {
    setEnvoi(true);
    try {
      const c = await action();
      setPhoto(c.photo ?? null);
      setValidee(!!c.photo_validee);
      toast.success(message);
      onChange();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Photo refusée."));
    } finally {
      setEnvoi(false);
    }
  };
  return (
    <div className="rounded-2xl border border-gray-100 p-3 space-y-2">
      <p className="text-xs font-bold text-dark uppercase tracking-wide">Photo de profil</p>
      <div className="flex items-center gap-3">
        {photo ? <img src={photo} alt="" className="w-16 h-16 rounded-full object-cover border" /> : <div className="w-16 h-16 rounded-full bg-gray-100" />}
        <div className="space-y-1 text-sm">
          <input type="file" accept="image/jpeg,image/png,image/webp" disabled={envoi} className="text-sm"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) agir(() => envoyerPhotoChauffeur(chauffeur.id, f), "Photo ajoutée : validez-la."); }} />
          {photo && !validee && (
            <button type="button" disabled={envoi} onClick={() => agir(() => validerPhotoChauffeur(chauffeur.id), "Photo validée.")}
              className="px-3 py-1.5 rounded-xl bg-primary text-white text-xs font-bold">Valider la photo</button>
          )}
          {validee && <p className="text-xs text-green-700">Validée : le chauffeur peut recevoir des courses.</p>}
        </div>
      </div>
    </div>
  );
}

/** The ratings, incidents and level history of a driver; an incident is recorded here. */
function Suivi({ chauffeur, onFermer }: { chauffeur: ChauffeurAdmin; onFermer: () => void }) {
  const { data, refetch } = useQuery({ queryKey: [...clesTransferts.admin, "suivi", chauffeur.id], queryFn: () => lireSuiviChauffeur(chauffeur.id) });
  const [incident, setIncident] = useState<{ type: TypeIncident; date: string; description: string; reference: string }>(
    { type: "retard", date: new Date().toISOString().slice(0, 10), description: "", reference: "" });
  const signaler = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await signalerIncident(chauffeur.id, incident);
      toast.success("Incident enregistré.");
      setIncident({ ...incident, description: "", reference: "" });
      refetch();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Incident refusé."));
    }
  };
  return (
    <section className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" aria-label="Suivi du chauffeur">
      <div className="flex justify-between gap-2"><h2 className="font-heading font-bold text-dark">Suivi · {chauffeur.prenom} {chauffeur.nom}</h2>
        <button onClick={onFermer} className="text-sm font-semibold text-brand">Fermer</button></div>
      <div className="grid md:grid-cols-2 gap-4 text-sm">
        <div><h3 className="font-semibold text-dark mb-1">Avis des voyageurs</h3>
          <ul className="divide-y divide-gray-50">
            {data?.avis.map((a, i) => <li key={i} className="py-1.5"><strong>{a.note}/5</strong> <span className="text-muted">· ponctualité {a.ponctualite}, conduite {a.conduite}, amabilité {a.amabilite} · {a.cree_le.slice(0, 10)}</span>
              {a.commentaire && <span className="block text-xs text-muted">{a.commentaire}</span>}</li>)}
            {data?.avis.length === 0 && <li className="py-1.5 text-muted">Aucun avis pour l&apos;instant.</li>}
          </ul></div>
        <div><h3 className="font-semibold text-dark mb-1">Incidents</h3>
          <ul className="divide-y divide-gray-50">
            {data?.incidents.map((x) => <li key={x.id} className="py-1.5"><Pill ton={x.type === "grave" || x.type === "accident" ? "rouge" : x.type === "autre" ? "gris" : "orange"}>{INCIDENTS[x.type] ?? x.type}</Pill> <span className="text-muted">{x.date}{x.reference && ` · ${x.reference}`}</span>
              <span className="block text-xs">{x.description}</span></li>)}
            {data?.incidents.length === 0 && <li className="py-1.5 text-muted">Aucun incident.</li>}
          </ul>
          <form onSubmit={signaler} className="grid grid-cols-2 gap-2 mt-2">
            <Liste value={incident.type} onChange={(e) => setIncident({ ...incident, type: e.target.value as TypeIncident })}
              options={(Object.keys(INCIDENTS) as TypeIncident[]).map((value) => ({ value, label: INCIDENTS[value] }))} />
            <Saisie type="date" value={incident.date} onChange={(e) => setIncident({ ...incident, date: e.target.value })} />
            <Saisie placeholder="Ce qui s'est passé" value={incident.description} onChange={(e) => setIncident({ ...incident, description: e.target.value })} />
            <Saisie placeholder="Transfert ou location (facultatif)" value={incident.reference} onChange={(e) => setIncident({ ...incident, reference: e.target.value })} />
            <button type="submit" className="col-span-2 px-3 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Enregistrer l&apos;incident</button>
          </form></div>
      </div>
      {!!data?.niveaux.length && (
        <div className="text-sm"><h3 className="font-semibold text-dark mb-1">Historique des niveaux</h3>
          <ul className="divide-y divide-gray-50">{data.niveaux.map((n, i) => <li key={i} className="py-1.5">{n.le.slice(0, 10)} · {libelleHistorique(n.avant)} → <strong>{libelleHistorique(n.apres)}</strong> <span className="text-muted">(proposé : {libelleHistorique(n.propose)}){n.motif && ` · ${n.motif}`}</span></li>)}</ul></div>
      )}
    </section>
  );
}

/** The quarterly review: the level each driver's figures give, validated or corrected by the team. */
function RevueNiveaux() {
  const queryClient = useQueryClient();
  const { data, refetch } = useQuery({ queryKey: [...clesTransferts.admin, "niveaux"], queryFn: lireRevueNiveaux });
  const garder = async (l: LigneRevueNiveaux, niveau: keyof typeof NIVEAUX) => {
    let motif = "";
    if (niveau !== l.propose) {
      motif = window.prompt(`Le niveau proposé est ${NIVEAUX[l.propose].libelle}. Pourquoi garder ${NIVEAUX[niveau].libelle} pour ${l.nom} ?`) ?? "";
      if (!motif) return;
    }
    try {
      await validerNiveau(l.chauffeur_id, niveau, motif);
      toast.success(`${l.nom} : ${NIVEAUX[niveau].libelle}.`);
      refetch();
      queryClient.invalidateQueries({ queryKey: clesTransferts.admin });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Niveau refusé."));
    }
  };
  const colonnes: Colonne<LigneRevueNiveaux>[] = [
    { titre: "Chauffeur", masquerMobile: true, cellule: (l) => <strong>{l.nom}</strong> },
    { titre: "Missions", cellule: (l) => <span className="tabular-nums">{l.chiffres.courses} / {l.courses_requises}{l.fondateur && <> <Pill ton="bleu">Fondateur</Pill></>}</span> },
    { titre: "Note", cellule: (l) => <span className="tabular-nums">{l.chiffres.note === null ? "—" : `${Number(l.chiffres.note).toLocaleString("fr-FR")} (${l.chiffres.avis} avis)`}</span> },
    { titre: "Incidents", cellule: (l) => {
      const liste = ([["graves", "grave"], ["retards", "retard > 15 min"], ["absences", "absence"], ["plaintes", "plainte fondée"], ["accidents", "accident responsable"]] as const)
        .filter(([cle]) => l.chiffres[cle] > 0).map(([cle, nom]) => `${l.chiffres[cle]} ${nom}`);
      return <span className="text-xs">{liste.length ? liste.join(" · ") : "Aucun"}</span>;
    } },
    { titre: "Actuel → proposé", cellule: (l) => <span className="flex gap-1"><Pill ton={NIVEAUX[l.niveau].ton}>{NIVEAUX[l.niveau].libelle}</Pill>→<Pill ton={NIVEAUX[l.propose].ton}>{NIVEAUX[l.propose].libelle}</Pill></span> },
  ];
  return (
    <section className="space-y-2 pt-4" aria-label="Revue des niveaux">
      <h2 className="font-heading font-bold text-dark">Revue des niveaux du trimestre</h2>
      <p className="text-xs text-muted">Chiffres depuis le {data?.depuis.slice(0, 10)} (charte B6) : Excellence à partir de {data?.seuils.chauffeur_excellence_courses} missions
        ({data?.seuils.chauffeur_excellence_courses_fondateur} pour un chauffeur du Programme Fondateurs), une note de {data?.seuils.chauffeur_excellence_note} au moins,
        et sur la période ni retard de plus de 15 min, ni absence, ni plainte fondée, ni accident responsable, ni incident grave ; sinon Standard. Les seuils se modifient dans Finance → Paramètres.</p>
      <AdminTable colonnes={colonnes} lignes={data?.chauffeurs} cle={(l) => String(l.chauffeur_id)} titreMobile={(l) => <strong>{l.nom}</strong>}
        actions={(l) => (
          <>
            <ActionButton onClick={() => garder(l, l.propose)}>Valider {NIVEAUX[l.propose].libelle}</ActionButton>
            {(["standard", "excellence"] as const).filter((n) => n !== l.propose).map((n) => (
              <ActionButton key={n} onClick={() => garder(l, n)}>{NIVEAUX[n].libelle}</ActionButton>
            ))}
          </>
        )} />
    </section>
  );
}
