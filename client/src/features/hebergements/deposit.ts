import type { DepositRules } from "@/types/api/paiement";

/**
 * Escrowed deposit of a stay, for the host's preview only (the API computes the real amount, ADR-036): the rate of
 * the nights' price, rounded, capped by the absolute net; 0 below the minimum.
 */
export function escrowAmount(nightsPrice: number, rate: number, rules: DepositRules): number {
  const rounding = rules.rounding || 1;
  const rounded = Math.round((nightsPrice * rate) / 100 / rounding) * rounding;
  const amount = Math.min(rounded, rules.ceiling);
  return amount >= rules.minimum ? amount : 0;
}

/** Damages the enhanced guarantee covers. */
export function guaranteeCover(fee: number, rules: DepositRules): number {
  return fee * rules.guarantee_multiple;
}
