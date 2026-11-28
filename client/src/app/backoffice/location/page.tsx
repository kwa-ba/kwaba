"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import Lieux from "@/features/locations/admin/Lieux";
import Regles from "@/features/locations/admin/Regles";
import Suivi from "@/features/locations/admin/Suivi";

const ONGLETS = [
  { id: "suivi", label: "Locations", Composant: Suivi },
  { id: "lieux", label: "Lieux de remise", Composant: Lieux },
  { id: "regles", label: "Règles", Composant: Regles },
];

const DEPLACES: Record<string, string> = { categories: "vehicules", loueurs: "proprietaires" };

function Location() {
  const router = useRouter();
  const pathname = usePathname();
  const onglet = useSearchParams().get("onglet") ?? "suivi";
  const { Composant } = ONGLETS.find((o) => o.id === onglet) ?? ONGLETS[0];
  // Former links: the vehicles and the owners are now in Mobilité
  const deplace = DEPLACES[onglet];
  useEffect(() => {
    if (deplace) router.replace(`/backoffice/mobilite?onglet=${deplace}`);
  }, [deplace, router]);
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Location de voiture</h1>
        <p className="text-muted text-sm mt-1">Locations et chauffeurs à attribuer, lieux de remise et règles. Véhicules, propriétaires et chauffeurs : Mobilité.</p>
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

export default function LocationPage() {
  return <Suspense><Location /></Suspense>;
}
