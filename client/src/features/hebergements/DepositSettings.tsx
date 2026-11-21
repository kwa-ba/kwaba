"use client";

import { useTranslations } from "next-intl";
import { useConfigPaiement } from "@/features/paiements";
import { useFormat } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DepositOption } from "@/types/api/models";
import { escrowAmount, guaranteeCover } from "./deposit";

export interface DepositValue {
  option: DepositOption;
  rate: string;
  fee: string;
}

const OPTIONS: DepositOption[] = ["none", "enhanced_guarantee", "escrow"];
// Nights shown in the example of the escrowed deposit
const EXAMPLE_NIGHTS = [2, 7];

/**
 * Deposit chosen by the host for a listing (ADR-036): none, the enhanced guarantee (a fee the traveller pays, which
 * covers damages up to 5 times it) or the escrowed deposit (a rate of the nights' price, held by Kwa-Ba). The API
 * checks every value; this screen shows the rules and an example.
 */
export default function DepositSettings({ value, onChange, nightPrice, inputClass, error }: {
  value: DepositValue; onChange: (value: DepositValue) => void; nightPrice: number; inputClass: string;
  error?: React.ReactNode;
}) {
  const t = useTranslations("deposit");
  const { formatFcfa } = useFormat();
  const { data: config } = useConfigPaiement();
  const rules = config?.deposit;
  if (!rules) return null;

  const rate = Number(value.rate) || 0;
  const fee = Number(value.fee) || 0;
  const disponibles = OPTIONS.filter((o) => o !== "escrow" || rules.escrow_open || value.option === "escrow");

  return (
    <div className="space-y-3">
      <div className="grid sm:grid-cols-3 gap-2" role="radiogroup" aria-label={t("titre")}>
        {disponibles.map((option) => (
          <button key={option} type="button" role="radio" aria-checked={value.option === option}
            onClick={() => onChange({ ...value, option, rate: option === "escrow" && !value.rate ? String(rules.rate_proposed) : value.rate })}
            className={cn("text-left p-3 rounded-xl border text-sm",
              value.option === option ? "border-primary bg-primary/5" : "border-gray-200 hover:border-gray-300")}>
            <span className="block font-bold text-dark">{t(`${option}.nom`)}</span>
            <span className="block text-xs text-gray-500 mt-0.5">{t(`${option}.regle`)}</span>
          </button>
        ))}
      </div>
      {!rules.escrow_open && <p className="text-xs text-gray-500">{t("sequestreFerme")}</p>}

      {value.option === "enhanced_guarantee" && (
        <div>
          <label className="block text-xs font-bold text-dark mb-1" htmlFor="deposit-fee">{t("forfait")}</label>
          <input id="deposit-fee" type="number" min={1} inputMode="numeric" className={inputClass} value={value.fee}
            onChange={(e) => onChange({ ...value, fee: e.target.value })} placeholder="5000" />
          <p className="text-xs text-gray-500 mt-1.5">
            {fee > 0 ? t("couverture", { montant: formatFcfa(guaranteeCover(fee, rules)) }) : t("forfaitAide")}
          </p>
        </div>
      )}

      {value.option === "escrow" && (
        <div>
          <label className="block text-xs font-bold text-dark mb-1" htmlFor="deposit-rate">{t("taux", { max: rules.rate_max })}</label>
          <input id="deposit-rate" type="number" min={1} max={rules.rate_max} step="0.5" inputMode="decimal"
            className={inputClass} value={value.rate} onChange={(e) => onChange({ ...value, rate: e.target.value })} />
          {rate > rules.rate_warning && <p role="status" className="text-xs text-amber-700 mt-1.5">{t("alerte", { seuil: rules.rate_warning })}</p>}
          {nightPrice > 0 && rate > 0 && (
            <ul className="text-xs text-gray-600 mt-1.5 space-y-0.5">
              {EXAMPLE_NIGHTS.map((nuits) => {
                const montant = escrowAmount(nuits * nightPrice, rate, rules);
                return <li key={nuits}>{montant ? t("exemple", { nuits, montant: formatFcfa(montant) }) : t("exempleSous", { nuits, minimum: formatFcfa(rules.minimum) })}</li>;
              })}
            </ul>
          )}
          <p className="text-xs text-gray-500 mt-1.5">{t("sequestreAide", { plafond: formatFcfa(rules.ceiling) })}</p>
        </div>
      )}
      {error}
    </div>
  );
}
