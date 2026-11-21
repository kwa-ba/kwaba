import Depenses from "@/features/finance/admin/Depenses";

export default function DepensesPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Dépenses</h1>
        <p className="text-muted text-sm mt-1">Chaque charge de Kwa-Ba saisie avec son justificatif : elle entre au grand livre et au résultat, et Kwa-Ba doit la somme à l&apos;associé qui l&apos;a avancée.</p>
      </div>
      <Depenses />
    </div>
  );
}
