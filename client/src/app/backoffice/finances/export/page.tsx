import ExportComptable from "@/features/finance/admin/ExportComptable";

export default function ExportPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Export comptable</h1>
        <p className="text-muted text-sm mt-1">Le fichier des écritures pour le cabinet comptable, prêt à importer.</p>
      </div>
      <ExportComptable />
    </div>
  );
}
