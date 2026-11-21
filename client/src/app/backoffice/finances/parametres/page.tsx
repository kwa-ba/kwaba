import Parametres from "@/features/finance/admin/Parametres";

export default function ParametresPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Paramètres</h1>
        <p className="text-muted text-sm mt-1">Toutes les valeurs que l&apos;équipe décide (taux, forfaits, plafonds, délais, seuils), avec leur source et l&apos;historique daté de chaque changement : qui, quand, avant, après et pourquoi.</p>
      </div>
      <Parametres />
    </div>
  );
}
