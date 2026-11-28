"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import Aeroports from "@/features/transferts/admin/Aeroports";
import Suivi from "@/features/transferts/admin/Suivi";

const ONGLETS = [
  { id: "suivi", label: "Transferts", Composant: Suivi },
  { id: "aeroports", label: "Aéroports et tarifs", Composant: Aeroports },
];

function Transferts() {
  const router = useRouter();
  const pathname = usePathname();
  const onglet = useSearchParams().get("onglet") ?? "suivi";
  const { Composant } = ONGLETS.find((o) => o.id === onglet) ?? ONGLETS[0];
  // Former link: the drivers are now in Mobilité (one registry for transfers and rentals)
  useEffect(() => {
    if (onglet === "chauffeurs") router.replace("/backoffice/mobilite?onglet=chauffeurs");
  }, [onglet, router]);
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Transferts aéroport</h1>
        <p className="text-muted text-sm mt-1">Chauffeurs à attribuer, aéroports et tarifs. Le registre des chauffeurs est dans Mobilité.</p>
      </div>
      <div role="tablist" className="flex gap-5 overflow-x-auto scrollbar-hide border-b border-gray-200">
        {ONGLETS.map((o) => (
          <button key={o.id} role="tab" aria-selected={onglet === o.id} onClick={() => router.replace(`${pathname}?onglet=${o.id}`)}
            className={cn("relative zone-tactile pb-3 text-sm font-bold whitespace-nowrap border-b-2 transition-colors",
              onglet === o.id ? "text-brand border-primary" : "text-gray-500 border-transparent hover:text-dark")}>
            {o.label}
          </button>
        ))}
      </div>
      <Composant />
    </div>
  );
}

export default function TransfertsPage() {
  return <Suspense><Transferts /></Suspense>;
}
