"use client";

import { useTranslations } from "next-intl";
import { useFormat } from "@/lib/format";

interface Props {
  /** Escrowed deposit, given back after the stay */
  deposit: number;
  /** Enhanced guarantee fee, kept unless the host cancels */
  guaranteeFee: number;
  /** Damages the guarantee covers */
  guaranteeCover: number;
  amountClassName?: string;
}

/** Deposit lines of a stay's price breakdown (ADR-036): shown to the traveller before the payment. */
export default function StayDepositLines({ deposit, guaranteeFee, guaranteeCover, amountClassName = "text-dark" }: Props) {
  const t = useTranslations("deposit.stay");
  const { formatPrice } = useFormat();
  return (
    <>
      {guaranteeFee > 0 && (
        <div className="flex justify-between gap-2">
          <span className="text-gray-600">
            {t("guarantee")}
            <span className="block text-xs text-gray-500">{t("guaranteeHelp", { montant: formatPrice(guaranteeCover) })}</span>
          </span>
          <span className={amountClassName}>{formatPrice(guaranteeFee)}</span>
        </div>
      )}
      {deposit > 0 && (
        <div className="flex justify-between gap-2">
          <span className="text-gray-600">
            {t("escrow")}
            <span className="block text-xs text-gray-500">{t("escrowHelp")}</span>
          </span>
          <span className={amountClassName}>{formatPrice(deposit)}</span>
        </div>
      )}
    </>
  );
}
