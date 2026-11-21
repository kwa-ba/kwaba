import LivreJournal from "@/features/finance/admin/LivreJournal";

export default function LivreJournalPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Livre-journal</h1>
        <p className="text-muted text-sm mt-1">Chaque mouvement en deux écritures de même montant, au débit et au crédit, dans l&apos;ordre des dates. Les deux totaux sont toujours égaux.</p>
      </div>
      <LivreJournal />
    </div>
  );
}
