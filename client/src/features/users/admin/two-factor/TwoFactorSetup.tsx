"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { apiErrorMessage, estErreurApi } from "@/lib/api";
import type { TwoFactorSetup as Setup } from "@/types/api/admin";
import { confirmTwoFactorSetup, startTwoFactorSetup } from "../../api";
import { TWO_FACTOR_KEY } from "../../hooks";
import BackupCodes from "./BackupCodes";
import CodeInput from "./CodeInput";
import SetupFinish from "./SetupFinish";
import SetupKey from "./SetupKey";
import Step from "./Step";
import TwoFactorFrame from "./TwoFactorFrame";

const carte = "bg-surface rounded-3xl border border-gray-100 shadow-card p-5 sm:p-7";

/** Setup of the second factor (ADR-028): add the app, confirm a first code, keep the backup codes, then a new code. */
export default function TwoFactorSetup({ email }: { email: string }) {
  const queryClient = useQueryClient();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [erreurSetup, setErreurSetup] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [noted, setNoted] = useState(false);
  // One secret per screen: a second call would replace the one already shown (React runs effects twice in development)
  const demande = useRef(false);

  useEffect(() => {
    if (demande.current) return;
    demande.current = true;
    startTwoFactorSetup().then(setSetup).catch((err) => {
      // Already enabled in another tab: the guard shows the code screen instead
      if (estErreurApi(err) && err.response?.status === 409) queryClient.invalidateQueries({ queryKey: TWO_FACTOR_KEY });
      else setErreurSetup(apiErrorMessage(err));
    });
  }, [queryClient]);

  const confirmer = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      setCodes(await confirmTwoFactorSetup(code));
    } catch (err) {
      setErreur(apiErrorMessage(err));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <TwoFactorFrame email={email} wide>
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-amber-200 bg-amber-50 text-[11px] font-bold uppercase tracking-wider text-amber-800">
        <ShieldCheck size={14} aria-hidden /> Étape obligatoire
      </span>
      <h1 className="font-heading font-bold text-dark text-2xl sm:text-3xl mt-4">Activez la double authentification</h1>
      <p className="text-muted mt-3 max-w-2xl">
        Le back-office donne accès aux données des hôtes, des voyageurs et aux paiements. Il est réservé aux comptes
        protégés par un code à usage unique. Cette étape n&apos;est demandée qu&apos;une seule fois.
      </p>

      <div className="grid md:grid-cols-2 gap-5 mt-8 items-start">
        <div className={`${carte} space-y-7`}>
          <Step n={1} done={!!codes} title="Associez votre application"
            text="Scannez le QR code avec Google Authenticator, Microsoft Authenticator, Authy ou 1Password.">
            {setup ? <SetupKey setup={setup} /> : erreurSetup
              ? <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-xl p-3">{erreurSetup}</p>
              : <div className="h-40 rounded-2xl bg-gray-50 animate-pulse" />}
          </Step>
          <hr className="border-gray-100" />
          <Step n={2} done={!!codes} title="Saisissez le premier code"
            text="L'application affiche un code à 6 chiffres, renouvelé toutes les 30 secondes.">
            {codes ? (
              <p className="flex items-center gap-2 text-sm font-bold text-brand">
                <CheckCircle2 size={16} aria-hidden /> Code validé. Votre application est bien associée.
              </p>
            ) : (
              <form onSubmit={confirmer} className="space-y-2">
                <label htmlFor="premier-code" className="block text-sm font-bold text-dark">Code à 6 chiffres</label>
                <div className="flex gap-2">
                  <CodeInput id="premier-code" value={code} onChange={setCode} invalid={!!erreur} disabled={!setup || envoi} />
                  <button type="submit" disabled={!setup || envoi || code.length !== 6}
                    className="px-5 rounded-xl bg-primary text-white text-sm font-bold hover:bg-primary-600 disabled:opacity-50">
                    Vérifier
                  </button>
                </div>
                {erreur && <p role="alert" className="text-sm text-red-700">{erreur}</p>}
              </form>
            )}
          </Step>
        </div>

        <div className={carte}>
          <Step n={3} done={noted} title="Conservez vos codes de secours"
            text="Ils vous permettent de vous connecter si vous perdez votre téléphone. Chaque code ne fonctionne qu'une seule fois.">
            {codes
              ? <BackupCodes codes={codes} account={email} noted={noted} onNoted={setNoted} />
              : <p className="text-sm text-muted bg-gray-50 rounded-xl p-4">Vos codes apparaîtront après la validation du premier code.</p>}
          </Step>
        </div>
      </div>

      <SetupFinish ready={!!codes && noted} />
    </TwoFactorFrame>
  );
}
