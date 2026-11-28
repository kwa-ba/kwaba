"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Champ, Saisie, erreursApi } from "@/components/backoffice/Panneau";
import { formatDate } from "@/lib/utils";
import type { AdminStayDeposit } from "@/types/api/admin";
import { claimStayDeposit, decideStayDeposit, type StayDepositAction } from "../api";

type Props = { reservationId: string; caution: AdminStayDeposit };

/** Sends an action on the deposit, then refreshes the booking's page. */
function useDepositAction(reservationId: string, send: (id: string, action: StayDepositAction) => Promise<unknown>) {
  const queryClient = useQueryClient();
  const [erreurs, setErreurs] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);

  const envoyer = async (action: StayDepositAction, succes: string) => {
    setEnvoi(true);
    setErreurs({});
    try {
      await send(reservationId, action);
      toast.success(succes);
      await queryClient.invalidateQueries({ queryKey: ["admin", "reservation", reservationId] });
      return true;
    } catch (err) {
      setErreurs(erreursApi(err));
      return false;
    } finally {
      setEnvoi(false);
    }
  };
  return { erreurs, envoi, envoyer };
}

function Pieces({ deja, onChange }: { deja: number; onChange: (files: File[]) => void }) {
  return (
    <Champ label="Pièces justificatives" aide={`Photos, constat ou devis (PDF, JPEG, PNG, 10 Mo au plus). Déjà jointes : ${deja}.`}>
      <input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" className="text-sm"
        onChange={(e) => onChange(Array.from(e.target.files ?? []))} />
    </Champ>
  );
}

function Bouton({ envoi, onClick, children }: { envoi: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} disabled={envoi}
      className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
      {envoi ? "Enregistrement…" : children}
    </button>
  );
}

/** Step 1 (terms of sale 13.6): the damage the host reported, within 48 h of the departure. It stays held; the rest of
 * the deposit goes back to the traveller at the end of the reporting period. */
export function ClaimForm({ reservationId, caution }: Props) {
  const [form, setForm] = useState({ montant: caution.reclame ? String(caution.reclame) : "", motif: caution.reclamation_motif });
  const [pieces, setPieces] = useState<File[]>([]);
  const { erreurs, envoi, envoyer } = useDepositAction(reservationId, claimStayDeposit);

  const enregistrer = async () => {
    const montant = Number(form.montant || 0);
    if (await envoyer({ ...form, montant, justificatifs: pieces }, montant > 0 ? "Réclamation enregistrée : ce montant reste gardé" : "Réclamation retirée")) setPieces([]);
  };

  return (
    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
      <p className="text-xs text-muted">
        Dommage signalé par l&apos;hôte{caution.reclamation_avant ? ` (jusqu'au ${formatDate(caution.reclamation_avant)})` : ""} : le montant réclamé reste gardé, le reste de la caution est rendu au voyageur à la fin du délai de signalement. 0 retire la réclamation.
      </p>
      {erreurs.detail && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurs.detail}</p>}
      <Champ label="Montant réclamé (FCFA)" erreur={erreurs.montant}>
        <Saisie type="number" min={0} max={caution.montant} value={form.montant} onChange={(e) => setForm({ ...form, montant: e.target.value })} />
      </Champ>
      <Champ label="Dommage signalé" aide="Communiqué au voyageur" erreur={erreurs.motif}>
        <Saisie value={form.motif} maxLength={255} onChange={(e) => setForm({ ...form, motif: e.target.value })} placeholder="Table basse cassée (photos de l'hôte)" />
      </Champ>
      <Pieces deja={caution.justificatifs} onChange={setPieces} />
      <Bouton envoi={envoi} onClick={enregistrer}>Enregistrer la réclamation</Bouton>
    </div>
  );
}

/** Step 2: the team's motivated decision, after the traveller's answer. What it sets aside goes back at once; the
 * withholding is paid to the host once the traveller's contestation period is over. A new decision can only lower it. */
export function DecisionForm({ reservationId, caution }: Props) {
  const plafond = caution.decidee_le ? caution.retenue : caution.reclame;
  const [form, setForm] = useState({
    montant: caution.decidee_le ? String(caution.retenue) : "", motif: caution.motif, cgv_article: caution.cgv_article || "13.6",
  });
  const [pieces, setPieces] = useState<File[]>([]);
  const { erreurs, envoi, envoyer } = useDepositAction(reservationId, decideStayDeposit);

  const enregistrer = async () => {
    const montant = Number(form.montant || 0);
    if (await envoyer({ ...form, montant, justificatifs: pieces }, montant > 0 ? "Décision enregistrée : le voyageur peut la contester" : "Décision enregistrée : rien n'est retenu")) setPieces([]);
  };

  return (
    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
      <p className="text-xs text-muted">
        {caution.decidee_le
          ? "Réexamen après une contestation du voyageur : la retenue ne peut que baisser."
          : "Décision motivée, après la réponse du voyageur (48 h), en tenant compte de l'usure normale."}{" "}
        Au plus {plafond} FCFA. 0 rend tout au voyageur.
      </p>
      {erreurs.detail && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurs.detail}</p>}
      <Champ label="Montant retenu (FCFA)" erreur={erreurs.montant}>
        <Saisie type="number" min={0} max={plafond} value={form.montant} onChange={(e) => setForm({ ...form, montant: e.target.value })} />
      </Champ>
      <Champ label="Motif" aide="Communiqué au voyageur et à l'hôte" erreur={erreurs.motif}>
        <Saisie value={form.motif} maxLength={255} onChange={(e) => setForm({ ...form, motif: e.target.value })} />
      </Champ>
      <Champ label="Article des conditions générales" aide="Fondement cité dans l'avis de retenue" erreur={erreurs.cgv_article}>
        <Saisie value={form.cgv_article} maxLength={30} onChange={(e) => setForm({ ...form, cgv_article: e.target.value })} />
      </Champ>
      <Pieces deja={caution.justificatifs} onChange={setPieces} />
      <Bouton envoi={envoi} onClick={enregistrer}>Enregistrer la décision</Bouton>
    </div>
  );
}
