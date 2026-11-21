import Versements from "@/features/paiements/admin/Versements";

export default function VersementsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Versements aux partenaires</h1>
        <p className="text-muted text-sm mt-1">Ce que Kwa-Ba doit à chaque hôte, chauffeur et propriétaire de véhicule : date prévue, état, relance des versements en échec, et séjours annulés après leur versement.</p>
      </div>
      <Versements />
    </div>
  );
}
