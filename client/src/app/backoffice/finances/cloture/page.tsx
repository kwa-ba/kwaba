import Cloture from "@/features/finance/admin/Cloture";

export default function CloturePage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Clôture mensuelle</h1>
        <p className="text-muted text-sm mt-1">Les six contrôles d&apos;un mois et, quand ils sont tous verts, son verrouillage définitif.</p>
      </div>
      <Cloture />
    </div>
  );
}
