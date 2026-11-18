import Rapports from "@/features/finance/admin/Rapports";

export default function RapportsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Finance · Rapports</h1>
        <p className="text-muted text-sm mt-1">Les rapports enregistrés, un rapport libre sur un ou deux axes, et l&apos;enregistrement d&apos;un nouveau rapport sans développement.</p>
      </div>
      <Rapports />
    </div>
  );
}
