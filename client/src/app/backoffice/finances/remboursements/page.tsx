import Remboursements from "@/features/paiements/admin/Remboursements";

export default function RemboursementsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Remboursements</h1>
        <p className="text-muted text-sm mt-1">Rembourser un séjour depuis ses tarifs figés, et suivre chaque remboursement jusqu&apos;à son envoi.</p>
      </div>
      <Remboursements />
    </div>
  );
}
