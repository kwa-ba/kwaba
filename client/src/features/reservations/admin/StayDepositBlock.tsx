"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Champ, Saisie, erreursApi } from "@/components/backoffice/Panneau";
import { formatDate, formatPrice } from "@/lib/utils";
import type { AdminStayDeposit } from "@/types/api/admin";
import { withholdStayDeposit } from "../api";

/** Terms of sale: damages caused by the customer during a stay (article 13.6) */
const STAY_DEPOSIT_CGV_ARTICLE = "13.6";

/** Deposit of a stay in its back-office page (ADR-036, ADR-038): the enhanced guarantee, or the escrowed deposit with
 * the withholding for a damage reported by the host, entered before the worker gives the deposit back. */
export default function StayDepositBlock({ reservationId, caution }: { reservationId: string; caution: AdminStayDeposit }) {
  if (caution.option === "enhanced_guarantee") {
    return (
      <p className="text-sm text-gray-700">
        Garantie Kwa-Ba renforcée : forfait de {formatPrice(caution.garantie)}, dommages couverts jusqu&apos;à {formatPrice(caution.garantie_couverture)}.
      </p>
    );
  }
  if (!caution.montant) return <p className="text-sm text-muted">Sans caution.</p>;
  return (
    <>
      <p className="text-sm text-gray-700">
        Caution séquestrée de {formatPrice(caution.montant)}
        {caution.restituee_le
          ? ` · réglée le ${formatDate(caution.restituee_le)}${caution.document ? ` (${caution.document})` : ""}`
          : caution.date_limite ? ` · rendue au voyageur à partir du ${formatDate(caution.date_limite)}` : ""}
        {caution.retenue > 0 && ` · retenue de ${formatPrice(caution.retenue)} (${caution.motif}), versée à l'hôte`}
      </p>
      {!caution.restituee_le && <WithholdingForm reservationId={reservationId} caution={caution} />}
    </>
  );
}

function WithholdingForm({ reservationId, caution }: { reservationId: string; caution: AdminStayDeposit }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    montant: caution.retenue ? String(caution.retenue) : "", motif: caution.motif, cgv_article: caution.cgv_article || STAY_DEPOSIT_CGV_ARTICLE,
  });
  const [pieces, setPieces] = useState<File[]>([]);
  const [erreurs, setErreurs] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);

  const enregistrer = async () => {
    setEnvoi(true);
    setErreurs({});
    try {
      await withholdStayDeposit(reservationId, { ...form, montant: Number(form.montant || 0), justificatifs: pieces });
      toast.success(Number(form.montant) > 0 ? "Retenue enregistrée : elle sera versée à l'hôte" : "Retenue annulée");
      setPieces([]);
      await queryClient.invalidateQueries({ queryKey: ["admin", "reservation", reservationId] });
    } catch (err) {
      setErreurs(erreursApi(err));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
      <p className="text-xs text-muted">
        Dommage signalé par l&apos;hôte : la retenue lui est versée à part, le reste est rendu au voyageur à la fin du délai de signalement. 0 annule la retenue.
      </p>
      {erreurs.detail && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurs.detail}</p>}
      <Champ label="Montant retenu (FCFA)" erreur={erreurs.montant}>
        <Saisie type="number" min={0} max={caution.montant} value={form.montant} onChange={(e) => setForm({ ...form, montant: e.target.value })} />
      </Champ>
      <Champ label="Motif" aide="Communiqué au voyageur et à l'hôte" erreur={erreurs.motif}>
        <Saisie value={form.motif} maxLength={255} onChange={(e) => setForm({ ...form, motif: e.target.value })} placeholder="Table basse cassée (photos de l'hôte)" />
      </Champ>
      <Champ label="Article des conditions générales" aide="Fondement cité dans l'avis de retenue" erreur={erreurs.cgv_article}>
        <Saisie value={form.cgv_article} maxLength={30} onChange={(e) => setForm({ ...form, cgv_article: e.target.value })} />
      </Champ>
      <Champ label="Pièces justificatives" aide={`Obligatoire pour une retenue : photos, constat ou devis (PDF, JPEG, PNG, 10 Mo au plus). Déjà jointes : ${caution.justificatifs}.`}>
        <input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" className="text-sm"
          onChange={(e) => setPieces(Array.from(e.target.files ?? []))} />
      </Champ>
      <button type="button" onClick={enregistrer} disabled={envoi}
        className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
        {envoi ? "Enregistrement…" : "Enregistrer la retenue"}
      </button>
    </div>
  );
}
