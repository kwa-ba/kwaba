import BalanceGenerale from "@/features/finance/admin/BalanceGenerale";

export default function BalancePage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Balance générale</h1>
        <p className="text-muted text-sm mt-1">Pour chaque compte : solde d&apos;ouverture, débits et crédits de la période, solde de clôture. Le contrôle d&apos;ensemble des livres.</p>
      </div>
      <BalanceGenerale />
    </div>
  );
}
