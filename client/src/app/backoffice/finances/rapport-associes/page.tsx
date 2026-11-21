import { RapportAssocies } from "@/features/finance/admin/Pilotage";

export default function Page() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Rapport aux associés</h1>
        <p className="text-muted text-sm mt-1">Le rapport mensuel aux sept associés (pacte, art. 2.4) : les chiffres du mois et le commentaire du référent, à télécharger en PDF.</p>
      </div>
      <RapportAssocies />
    </div>
  );
}
