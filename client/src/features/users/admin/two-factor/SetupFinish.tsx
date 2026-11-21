"use client";

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import CodeInput from "./CodeInput";
import { SignOutButton } from "./TwoFactorFrame";
import { useVerifyCode } from "./useVerifyCode";

/** End of the setup: once the backup codes are noted, a new code of the app opens the back-office. The first code
 * cannot be used twice, which also shows that the app keeps producing codes. */
export default function SetupFinish({ ready }: { ready: boolean }) {
  const [code, setCode] = useState("");
  const { verifier, envoi, erreur } = useVerifyCode();

  const acceder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!(await verifier(code))) setCode("");
  };

  return (
    <div className="mt-6 flex flex-col-reverse sm:flex-row sm:items-end sm:justify-between gap-4">
      <SignOutButton />
      {ready ? (
        <form onSubmit={acceder} className="w-full sm:w-auto space-y-2">
          <label htmlFor="nouveau-code" className="block text-sm font-bold text-dark">
            Saisissez le nouveau code affiché par l&apos;application
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="sm:w-56">
              <CodeInput id="nouveau-code" value={code} onChange={setCode} invalid={!!erreur} disabled={envoi} autoFocus />
            </div>
            <button type="submit" disabled={envoi || code.length !== 6}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white text-sm font-bold hover:bg-primary-600 disabled:opacity-50">
              <ShieldCheck size={16} aria-hidden /> Activer et accéder au back-office
            </button>
          </div>
          {erreur && <p role="alert" className="text-sm text-red-700">{erreur} Attendez le code suivant de l&apos;application.</p>}
        </form>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-muted">Confirmez avoir noté vos codes de secours.</p>
          <button type="button" disabled
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gray-200 text-gray-500 text-sm font-bold">
            <ShieldCheck size={16} aria-hidden /> Activer et accéder au back-office
          </button>
        </div>
      )}
    </div>
  );
}
