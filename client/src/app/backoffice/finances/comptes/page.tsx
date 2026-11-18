import GrandLivreComptes from "@/features/finance/admin/GrandLivreComptes";

export default function GrandLivreComptesPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Grand-livre par compte</h1>
        <p className="text-muted text-sm mt-1">Les écritures d&apos;un compte et son solde ligne après ligne : combien doit-on à cet hôte, combien y a-t-il sur FedaPay.</p>
      </div>
      <GrandLivreComptes />
    </div>
  );
}
