import FondsGarantie from "@/features/finance/admin/FondsGarantie";

export default function FondsGarantiePage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Fonds de garantie</h1>
        <p className="text-muted text-sm mt-1">La part de l&apos;argent mise de côté pour la Garantie Kwa-Ba : dotée chaque mois, elle couvre les sinistres décidés et reste séparée de la trésorerie libre.</p>
      </div>
      <FondsGarantie />
    </div>
  );
}
