import { Inventaire } from "@/features/finance/admin/Pilotage";

export default function Page() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Livre d&apos;inventaire</h1>
        <p className="text-muted text-sm mt-1">L&apos;exercice comptable : amortissement de la Solution, écritures d&apos;inventaire, résultat, bilan et à-nouveaux de l&apos;année suivante.</p>
      </div>
      <Inventaire />
    </div>
  );
}
