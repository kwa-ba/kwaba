import ComptesAssocies from "@/features/finance/admin/ComptesAssocies";

export default function ComptesAssociesPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Comptes des associés</h1>
        <p className="text-muted text-sm mt-1">Ce que Kwa-Ba doit à chaque associé (dépenses avancées, avances, remboursements), lu au grand livre, avec le capital social et la part de chacun.</p>
      </div>
      <ComptesAssocies />
    </div>
  );
}
