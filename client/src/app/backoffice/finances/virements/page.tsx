import Virements from "@/features/finance/admin/Virements";

export default function VirementsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Virements et banque</h1>
        <p className="text-muted text-sm mt-1">L&apos;argent déplacé entre les comptes de Kwa-Ba (FedaPay, la banque), avec sa preuve, et les relevés de la banque rapprochés jour par jour.</p>
      </div>
      <Virements />
    </div>
  );
}
