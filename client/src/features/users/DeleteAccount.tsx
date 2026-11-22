"use client";

import { useState } from "react";
import { signOut } from "next-auth/react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { apiErrorMessage } from "@/lib/api";
import { accountDeletionBlockers, deleteMyAccount, requestAccountDeletionCode, type AccountDeletionBlocker } from "./api";

/**
 * Deletion of one's own account (ADR-039): a code is emailed, then typed to confirm. While something is still pending
 * (an upcoming stay, a payout to receive…), the API refuses and gives the reasons, shown as a list.
 */
export default function DeleteAccount() {
  const t = useTranslations("profilEdition");
  const locale = useLocale();
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blockers, setBlockers] = useState<AccountDeletionBlocker[]>([]);

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    setBlockers([]);
    try {
      await action();
    } catch (err) {
      const reasons = accountDeletionBlockers(err);
      if (reasons.length) setBlockers(reasons);
      else setError(apiErrorMessage(err, t("deleteError")));
    } finally {
      setPending(false);
    }
  }

  const askForCode = () =>
    run(async () => {
      await requestAccountDeletionCode();
      setCodeSent(true);
    });

  const confirm = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      await deleteMyAccount(code.trim());
      await signOut({ callbackUrl: locale === "en" ? "/en" : "/" });
    });
  };

  return (
    <section aria-labelledby="delete-account-title" className="mt-8 bg-background rounded-2xl border border-red-100 p-6 md:p-8">
      <h2 id="delete-account-title" className="font-heading font-bold text-lg text-dark">{t("deleteAccount")}</h2>
      <p className="text-sm text-gray-600 mt-2 max-w-2xl">
        {t.rich("deleteText", { lien: (x) => <Link href="/confidentialite#droits" className="text-brand underline">{x}</Link> })}
      </p>

      {blockers.length > 0 && (
        <div role="alert" className="mt-4 p-4 rounded-xl bg-amber-50 border border-amber-200 text-sm text-dark max-w-2xl">
          <p className="font-medium">{t("deleteBlocked")}</p>
          <ul className="list-disc pl-5 mt-2 space-y-1">
            {blockers.map((blocker) => <li key={blocker.code}>{blocker.detail}</li>)}
          </ul>
        </div>
      )}
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}

      {codeSent ? (
        <form onSubmit={confirm} className="mt-4 max-w-sm space-y-3">
          <p className="text-sm text-gray-600">{t("deleteCodeSent")}</p>
          <label htmlFor="delete-account-code" className="block text-sm font-medium text-dark">{t("deleteCodeLabel")}</label>
          <input
            id="delete-account-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full px-4 py-3 bg-surface border border-gray-200 rounded-xl text-base sm:text-sm text-dark tracking-widest focus:outline-hidden focus:border-red-600 focus:ring-2 focus:ring-red-600/20"
          />
          <div className="flex flex-col-reverse sm:flex-row gap-3">
            <button type="button" onClick={() => setCodeSent(false)} className="px-5 py-3 rounded-xl border border-gray-200 text-dark text-sm font-medium hover:bg-light-muted">
              {t("deleteCancel")}
            </button>
            <button type="submit" disabled={pending || code.trim().length !== 6} className="px-5 py-3 rounded-xl bg-red-600 text-white text-sm font-bold hover:bg-red-700 disabled:opacity-60">
              {pending ? t("deleteInProgress") : t("deleteConfirm")}
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={askForCode}
          disabled={pending}
          className="mt-4 px-5 py-3 rounded-xl border-2 border-red-600 text-red-700 text-sm font-bold hover:bg-red-50 disabled:opacity-60"
        >
          {t("deleteAskCode")}
        </button>
      )}
    </section>
  );
}
