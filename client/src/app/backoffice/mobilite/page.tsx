"use client";

import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import Chauffeurs from "@/features/transferts/admin/Chauffeurs";
import Categories from "@/features/locations/admin/Categories";
import Loueurs from "@/features/locations/admin/Loueurs";
import { TarifsMobilite } from "@/features/locations/admin/Regles";
import Gammes from "@/features/mobilite/admin/Gammes";

// The shared base of the two mobility products (harmonisation of 26 November 2026): one registry of drivers, of
// vehicles and of owners, one referential of ranges and of rates, for the transfers and the car hire alike
const ONGLETS = [
  { id: "chauffeurs", label: "Chauffeurs", Composant: Chauffeurs },
  { id: "vehicules", label: "Véhicules", Composant: Categories },
  { id: "proprietaires", label: "Propriétaires", Composant: Loueurs },
  { id: "gammes", label: "Gammes", Composant: Gammes },
  { id: "tarifs", label: "Tarifs & règles", Composant: TarifsMobilite },
];

function Mobilite() {
  const router = useRouter();
  const pathname = usePathname();
  const onglet = useSearchParams().get("onglet") ?? "chauffeurs";
  const { Composant } = ONGLETS.find((o) => o.id === onglet) ?? ONGLETS[0];
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">Mobilité</h1>
        <p className="text-muted text-sm mt-1">Le socle commun des transferts aéroport et de la location : chauffeurs, véhicules, propriétaires, gammes et tarifs. Un compte peut être à la fois chauffeur et propriétaire.</p>
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

export default function MobilitePage() {
  return <Suspense><Mobilite /></Suspense>;
}
