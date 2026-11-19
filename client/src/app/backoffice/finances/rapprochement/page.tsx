import Rapprochement from "@/features/finance/admin/Rapprochement";

export default function RapprochementPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Rapprochement FedaPay</h1>
        <p className="text-muted text-sm mt-1">Chaque journée terminée comparée sur trois colonnes : les enregistrements de Kwa-Ba, le compte FedaPay du grand livre et le relevé FedaPay avec ses frais réels. Un mois se clôture quand toutes ses journées sont vertes.</p>
      </div>
      <Rapprochement />
    </div>
  );
}
