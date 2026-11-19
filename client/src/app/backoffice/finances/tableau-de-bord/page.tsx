import { TableauDeBord } from "@/features/finance/admin/Pilotage";

export default function Page() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Tableau de bord</h1>
        <p className="text-muted text-sm mt-1">Les indicateurs du directeur financier, lus au grand livre : activité, revenu par offre, résultat, trésorerie en quatre poches, annulations, fiscalité et seuils des associés.</p>
      </div>
      <TableauDeBord />
    </div>
  );
}
