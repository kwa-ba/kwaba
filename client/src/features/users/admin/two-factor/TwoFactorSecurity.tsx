"use client";

import { AlertTriangle, ShieldCheck, ShieldOff } from "lucide-react";
import { useTwoFactorStatus } from "../../hooks";
import { resumeSetup } from "./postpone";

const dateHeure = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short" }) : "-";

// Below this, the admin is warned: a super admin resets the second factor to get new codes
const FEW_CODES = 3;

/** "Sécurité du compte" page of the back-office: state of the admin's own second factor (ADR-028). */
export default function TwoFactorSecurity() {
  const { data: status, isLoading } = useTwoFactorStatus();

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="font-heading font-bold text-dark text-2xl">Sécurité du compte</h1>
      <section className="bg-surface rounded-2xl border border-gray-100 p-5 sm:p-6 space-y-5">
        <div className="flex items-start gap-3">
          {status?.enabled
            ? <ShieldCheck size={24} aria-hidden className="text-brand shrink-0" />
            : <ShieldOff size={24} aria-hidden className="text-amber-600 shrink-0" />}
          <div>
            <h2 className="font-heading font-bold text-dark text-lg">Double authentification</h2>
            <p className="text-sm text-muted">
              {isLoading ? "Chargement…" : status?.enabled
                ? "Active : un code de votre application est demandé à la connexion et toutes les 12 heures."
                : "Inactive : votre accès au back-office ne repose que sur votre connexion."}
            </p>
          </div>
        </div>

        {status?.enabled ? (
          <dl className="grid sm:grid-cols-3 gap-4 text-sm">
            <div><dt className="text-muted">Activée le</dt><dd className="font-bold text-dark">{dateHeure(status.enabled_at)}</dd></div>
            <div><dt className="text-muted">Prochaine vérification</dt><dd className="font-bold text-dark">{dateHeure(status.expires_at)}</dd></div>
            <div><dt className="text-muted">Codes de secours restants</dt><dd className="font-bold text-dark">{status.backup_codes_left} sur 10</dd></div>
          </dl>
        ) : !isLoading && (
          <button type="button" onClick={resumeSetup}
            className="px-5 py-2.5 rounded-xl bg-primary text-white text-sm font-bold hover:bg-primary-600">
            Activer maintenant
          </button>
        )}

        {status?.enabled && status.backup_codes_left < FEW_CODES && (
          <p role="status" className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <AlertTriangle size={16} aria-hidden className="shrink-0 mt-0.5" />
            Il vous reste {status.backup_codes_left} code{status.backup_codes_left > 1 ? "s" : ""} de secours. Pour en
            obtenir de nouveaux, demandez à un super admin de réinitialiser votre double authentification, puis
            réactivez-la.
          </p>
        )}
      </section>
    </div>
  );
}
