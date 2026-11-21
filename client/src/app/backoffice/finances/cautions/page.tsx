import Cautions from "@/features/finance/admin/Cautions";

export default function CautionsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Registre des cautions</h1>
        <p className="text-muted text-sm mt-1">Chaque caution détenue pour un voyageur, sa date de restitution, et son document : reçu de restitution ou avis de retenue motivé.</p>
      </div>
      <Cautions />
    </div>
  );
}
