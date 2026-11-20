"use client";

import { useState } from "react";
import { Clock, ShieldCheck } from "lucide-react";
import CodeInput, { isComplete } from "./CodeInput";
import TwoFactorFrame from "./TwoFactorFrame";
import { useVerifyCode } from "./useVerifyCode";

/** Code asked at sign-in and every 12 hours (ADR-028). */
export default function TwoFactorPrompt() {
  const [backup, setBackup] = useState(false);
  const [code, setCode] = useState("");
  const { verifier, envoi, erreur } = useVerifyCode();

  const valider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!(await verifier(code))) setCode("");
  };

  const changerDeMode = () => {
    setBackup(!backup);
    setCode("");
  };

  return (
    <TwoFactorFrame>
      <form onSubmit={valider} className="bg-surface rounded-3xl border border-gray-100 shadow-card p-6 sm:p-9 text-center">
        <span className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary/10 text-brand">
          <ShieldCheck size={26} aria-hidden />
        </span>
        <h1 className="font-heading font-bold text-dark text-2xl mt-4">Vérification en deux étapes</h1>
        <p className="text-muted mt-2">
          {backup
            ? "Saisissez l'un de vos codes de secours. Il ne servira qu'une fois."
            : "Ouvrez votre application d'authentification et saisissez le code à 6 chiffres affiché."}
        </p>
        <div className="text-left mt-6 space-y-2">
          <label htmlFor="code-2fa" className="block text-sm font-bold text-dark">
            {backup ? "Code de secours" : "Code à 6 chiffres"}
          </label>
          <CodeInput key={backup ? "secours" : "appli"} id="code-2fa" value={code} onChange={setCode} backup={backup}
            invalid={!!erreur} disabled={envoi} autoFocus />
          {erreur && <p role="alert" className="text-sm text-red-700">{erreur}</p>}
        </div>
        <button type="submit" disabled={envoi || !isComplete(code, backup)}
          className="w-full mt-5 px-5 py-3 rounded-xl bg-primary text-white font-bold hover:bg-primary-600 disabled:bg-gray-200 disabled:text-gray-500">
          {envoi ? "Vérification…" : "Vérifier"}
        </button>
        <button type="button" onClick={changerDeMode} className="mt-5 text-sm font-bold text-brand underline underline-offset-4">
          {backup ? "Utiliser l'application" : "Utiliser un code de secours"}
        </button>
        <p className="mt-3 text-xs text-muted">Téléphone perdu ? Contactez un super admin.</p>
        <p className="flex items-center justify-center gap-2 mt-6 pt-5 border-t border-gray-100 text-sm text-muted">
          <Clock size={16} aria-hidden /> Cette vérification est redemandée toutes les 12 heures.
        </p>
      </form>
    </TwoFactorFrame>
  );
}
