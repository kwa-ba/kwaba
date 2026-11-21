import Validations from "@/features/finance/admin/Validations";

export default function ValidationsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Validations</h1>
        <p className="text-muted text-sm mt-1">Les remboursements et versements à partir du seuil attendent l&apos;accord d&apos;une deuxième personne.</p>
      </div>
      <Validations />
    </div>
  );
}
