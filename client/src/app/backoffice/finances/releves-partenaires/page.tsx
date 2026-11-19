import { RelevesPartenaires } from "@/features/finance/admin/Pilotage";

export default function Page() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Relevés des partenaires</h1>
        <p className="text-muted text-sm mt-1">Pour chaque hôte, chauffeur ou propriétaire : ce qui lui est dû, ce qui lui a été versé, les commissions de Kwa-Ba et son solde, par mois et sur l&apos;année.</p>
      </div>
      <RelevesPartenaires />
    </div>
  );
}
