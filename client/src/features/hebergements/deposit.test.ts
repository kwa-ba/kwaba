import { describe, expect, it } from "vitest";
import type { DepositRules } from "@/types/api/paiement";
import { escrowAmount, guaranteeCover } from "./deposit";

const RULES: DepositRules = {
  rate_max: 40, rate_proposed: 10, rate_warning: 20, minimum: 5000, ceiling: 150000, rounding: 500,
  guarantee_multiple: 5, escrow_open: true,
};

describe("escrowAmount", () => {
  it("follows the examples of the decision", () => {
    expect(escrowAmount(75000, 10, RULES)).toBe(7500);
    expect(escrowAmount(600000, 40, RULES)).toBe(150000);
  });

  it("gives no deposit below the minimum, and rounds to 500", () => {
    expect(escrowAmount(30000, 10, RULES)).toBe(0);
    expect(escrowAmount(77777, 10, RULES)).toBe(8000);
  });
});

it("covers five times the guarantee fee", () => {
  expect(guaranteeCover(5000, RULES)).toBe(25000);
});
