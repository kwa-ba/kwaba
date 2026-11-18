import Finances from "@/features/paiements/admin/Finances";

export default function EncaissementsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Encaissements et versements</h1>
        <p className="text-muted text-sm mt-1">Encaissements, remboursements, versements aux partenaires et revenu de Kwa-Ba sur une période, avec les exports. Calculé depuis les paiements, à comparer au grand livre.</p>
      </div>
      <Finances />
    </div>
  );
}
