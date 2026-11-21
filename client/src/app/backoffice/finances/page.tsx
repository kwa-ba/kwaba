import SyntheseFinance from "@/features/finance/admin/SyntheseFinance";

export default function FinancesPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Synthèse</h1>
        <p className="text-muted text-sm mt-1">Lu dans le grand livre : contrôle des invariants, les soldes qui ne se mélangent jamais, chaque compte d&apos;argent et les sommes dues par partenaire.</p>
      </div>
      <SyntheseFinance />
    </div>
  );
}
