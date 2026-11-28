"use client";

import { formatDate, formatPrice } from "@/lib/utils";
import type { AdminStayDeposit } from "@/types/api/admin";
import { ClaimForm, DecisionForm } from "./StayDepositForms";

/** Deposit of a stay in its back-office page (ADR-036, ADR-038, ADR-048): the enhanced guarantee, or the escrowed
 * deposit with the damage the host claims and the team's decision on it. */
export default function StayDepositBlock({ reservationId, caution }: { reservationId: string; caution: AdminStayDeposit }) {
  if (caution.option === "enhanced_guarantee") {
    return (
      <p className="text-sm text-gray-700">
        Garantie Kwa-Ba renforcée : forfait de {formatPrice(caution.garantie)}, dommages pris en charge à titre commercial jusqu&apos;à {formatPrice(caution.garantie_couverture)}.
      </p>
    );
  }
  if (!caution.montant) return <p className="text-sm text-muted">Sans caution.</p>;
  const enCours = !caution.restituee_le;
  return (
    <>
      <p className="text-sm text-gray-700">
        Caution séquestrée de {formatPrice(caution.montant)}
        {caution.restituee_le
          ? ` · réglée le ${formatDate(caution.restituee_le)}${caution.document ? ` (${caution.document})` : ""}`
          : caution.date_limite ? ` · rendue au voyageur à partir du ${formatDate(caution.date_limite)}` : ""}
      </p>
      <DisputeSummary caution={caution} />
      {enCours && !caution.decidee_le && !caution.part_rendue_le && <ClaimForm reservationId={reservationId} caution={caution} />}
      {enCours && caution.reclame > 0 && <DecisionForm reservationId={reservationId} caution={caution} />}
    </>
  );
}

function DisputeSummary({ caution }: { caution: AdminStayDeposit }) {
  if (!caution.reclame && !caution.retenue) return null;
  return (
    <ul className="mt-1 text-sm text-gray-700 space-y-0.5">
      {caution.reclame > 0 && <li>Dommage réclamé par l&apos;hôte : {formatPrice(caution.reclame)} ({caution.reclamation_motif})</li>}
      {caution.deja_rendu > 0 && <li>Déjà rendu au voyageur : {formatPrice(caution.deja_rendu)}</li>}
      {caution.decidee_le && (
        <li>
          Décision du {formatDate(caution.decidee_le)} : {caution.retenue > 0 ? `retenue de ${formatPrice(caution.retenue)} (${caution.motif})` : "aucune retenue"}
          {caution.retenue > 0 && caution.contestation_avant && !caution.restituee_le && ` · contestable jusqu'au ${formatDate(caution.contestation_avant)}, puis versée à l'hôte`}
        </li>
      )}
    </ul>
  );
}
