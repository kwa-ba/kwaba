"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import { Activity, ArrowLeft, CalendarCheck, CalendarCog, CalendarRange, Car, ClipboardCheck, Compass, FileText, HandHeart, Home, Landmark, LayoutDashboard, Menu, Percent, Plane, Route, ShieldAlert, ShieldCheck, Star, Users } from "lucide-react";
import Logo from "@/components/layout/Logo";
import MobileDrawer, { DrawerItem } from "@/components/layout/MobileDrawer";
import ThemeSelector from "@/components/layout/ThemeSelector";
import { cn } from "@/lib/utils";
import { useDroitsAdmin } from "@/features/users";
import { AlerteVerifications, useCompteursVerification } from "@/features/verifications";

type SousPage = { href: string; label: string };

const NAV: { href: string; label: string; icon: typeof Users; section: string; compteur?: boolean; permission?: string; sousPages?: SousPage[] }[] = [
  { href: "/backoffice", label: "Tableau de bord", icon: LayoutDashboard, section: "tableau-de-bord" },
  // Identity documents and visits are handled in the agent space, which admins share with field agents
  { href: "/agent", label: "Vérifications", icon: ClipboardCheck, section: "verifications", compteur: true },
  { href: "/backoffice/planning", label: "Planning des agents", icon: CalendarRange, section: "verifications" },
  { href: "/backoffice/utilisateurs", label: "Utilisateurs", icon: Users, section: "utilisateurs" },
  { href: "/backoffice/annonces", label: "Annonces", icon: Home, section: "annonces" },
  { href: "/backoffice/reservations", label: "Réservations", icon: CalendarCheck, section: "reservations" },
  { href: "/backoffice/avis", label: "Avis", icon: Star, section: "avis" },
  { href: "/backoffice/anti-fraude", label: "Anti-fraude", icon: ShieldAlert, section: "anti-fraude" },
  { href: "/backoffice/activity", label: "Journal d'activité", icon: Activity, section: "", permission: "activity_log" },
  { href: "/backoffice/transferts", label: "Transferts aéroport", icon: Plane, section: "transferts" },
  { href: "/backoffice/location", label: "Location de voiture", icon: Car, section: "location" },
  { href: "/backoffice/mobilite", label: "Mobilité", icon: Route, section: "mobilite" },
  { href: "/backoffice/experiences", label: "Expériences", icon: Compass, section: "experiences" },
  { href: "/backoffice/give", label: "Kwa-Ba Give", icon: HandHeart, section: "give" },
  { href: "/backoffice/documents", label: "Documents", icon: FileText, section: "documents" },
  // One heading for all the money pages (GL-1): its pages open below it while one of them is shown
  { href: "/backoffice/finances", label: "Finance", icon: Landmark, section: "finances", sousPages: [
    { href: "/backoffice/finances", label: "Synthèse" },
    { href: "/backoffice/finances/tableau-de-bord", label: "Tableau de bord" },
    { href: "/backoffice/finances/grand-livre", label: "Grand livre" },
    { href: "/backoffice/finances/livre-journal", label: "Livre-journal" },
    { href: "/backoffice/finances/comptes", label: "Grand-livre par compte" },
    { href: "/backoffice/finances/balance", label: "Balance générale" },
    { href: "/backoffice/finances/encaissements", label: "Encaissements et versements" },
    { href: "/backoffice/finances/versements", label: "Versements aux partenaires" },
    { href: "/backoffice/finances/rapprochement", label: "Rapprochement" },
    { href: "/backoffice/finances/virements", label: "Virements et banque" },
    { href: "/backoffice/finances/depenses", label: "Dépenses" },
    { href: "/backoffice/finances/associes", label: "Comptes des associés" },
    { href: "/backoffice/finances/fonds-garantie", label: "Fonds de garantie" },
    { href: "/backoffice/finances/remboursements", label: "Remboursements" },
    { href: "/backoffice/finances/validations", label: "Validations" },
    { href: "/backoffice/finances/cautions", label: "Cautions" },
    { href: "/backoffice/finances/rapports", label: "Rapports" },
    { href: "/backoffice/finances/releves-partenaires", label: "Relevés des partenaires" },
    { href: "/backoffice/finances/rapport-associes", label: "Rapport aux associés" },
    { href: "/backoffice/finances/parametres", label: "Paramètres" },
    { href: "/backoffice/finances/cloture", label: "Clôture mensuelle" },
    { href: "/backoffice/finances/inventaire", label: "Livre d'inventaire" },
    { href: "/backoffice/finances/export", label: "Export comptable" },
  ] },
  { href: "/backoffice/tarifs", label: "Tarifs", icon: Percent, section: "tarifs" },
  { href: "/backoffice/agenda", label: "Réglages agenda", icon: CalendarCog, section: "verifications", permission: "agenda_settings" },
  // Every admin: their own second factor (ADR-028)
  { href: "/backoffice/securite", label: "Sécurité du compte", icon: ShieldCheck, section: "" },
];

export default function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: session, status } = useSession();
  const actif = (href: string) => (href === "/backoffice" ? pathname === href : pathname.startsWith(href));
  const courant = NAV.find((n) => actif(n.href));
  // The first page of a heading shares its address: it is current only on that exact address
  const actifSousPage = (parent: string, href: string) => (href === parent ? pathname === href : pathname.startsWith(href));
  const sousPageCourante = courant?.sousPages?.find((p) => actifSousPage(courant.href, p.href));
  const [menuOuvert, setMenuOuvert] = useState(false);

  const estAdmin = session?.user?.role === "admin";
  const { data: droits } = useDroitsAdmin(estAdmin);
  // Limited admin: only their sections (the API refuses the others anyway)
  const menu = droits
    ? NAV.filter((n) => (!n.section || droits.sections.includes(n.section))
      && (!n.permission || droits.permissions.includes(n.permission)))
    : NAV.filter((n) => !n.permission);
  const { data: compteurs } = useCompteursVerification(estAdmin && (droits?.sections.includes("verifications") ?? false));
  const enAttente = compteurs?.total ?? 0;

  // Closes the mobile panel after every navigation
  useEffect(() => setMenuOuvert(false), [pathname]);

  if (status === "loading") return <div className="min-h-screen bg-canvas" />;

  // The middleware already filters; second check on the page (the backend remains the only judge: 403 otherwise)
  if (session?.user?.role !== "admin") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-6 text-center bg-canvas">
        <ShieldAlert size={40} className="text-red-600" />
        <p className="font-heading font-bold text-xl text-dark">Accès réservé aux administrateurs</p>
        <Link href="/" className="text-brand font-bold hover:underline">Retour au site</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas lg:flex">
      <aside className="hidden lg:flex lg:flex-col w-64 shrink-0 bg-surface border-r border-gray-100 sticky top-0 h-screen p-5">
        <Logo size="sm" />
        <p className="text-[11px] font-bold uppercase tracking-widest text-muted mt-2 mb-8">Back-office</p>
        <nav className="space-y-1 flex-1 overflow-y-auto -mx-1 px-1" aria-label="Back-office">
          {menu.map(({ href, label, icon: Icon, compteur, sousPages }) => (
            <div key={href}>
              <Link href={href} aria-current={!sousPages && actif(href) ? "page" : undefined}
                className={cn("flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium", actif(href) ? "bg-primary/10 text-brand dark:bg-gray-100 dark:text-dark" : "text-dark hover:bg-gray-50")}>
                <Icon size={18} /> {label}
                {compteur && <Pastille nombre={enAttente} className="ml-auto" />}
              </Link>
              {sousPages && actif(href) && (
                <ul className="mt-1 ml-[1.375rem] pl-3 border-l border-gray-100 space-y-0.5">
                  {sousPages.map((p) => (
                    <li key={p.href}>
                      <Link href={p.href} aria-current={actifSousPage(href, p.href) ? "page" : undefined}
                        className={cn("block px-3 py-2 rounded-lg text-sm", actifSousPage(href, p.href) ? "font-semibold text-brand dark:text-dark bg-gray-50" : "text-muted hover:text-dark hover:bg-gray-50")}>
                        {p.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </nav>
        <div className="border-t border-gray-100 pt-4">
          <ThemeSelector className="mb-3" />
          {droits?.lecture_seule && <p className="text-xs font-bold text-amber-800 bg-amber-50 rounded-lg px-2 py-1 mb-2">Lecture seule : aucune modification</p>}
          <p className="text-xs text-muted truncate">{session.user.email}</p>
          <Link href="/" className="mt-2 flex items-center gap-2 text-sm font-medium text-dark hover:text-brand"><ArrowLeft size={15} /> Retour au site</Link>
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        <header className="lg:hidden sticky top-0 z-40 bg-background border-b border-gray-100">
          <div className="flex items-center gap-2 px-4 h-14">
            <button onClick={() => setMenuOuvert(true)} aria-haspopup="dialog" aria-expanded={menuOuvert}
              aria-label={enAttente > 0 ? `Ouvrir le menu du back-office (${enAttente} vérification${enAttente > 1 ? "s" : ""} en attente)` : "Ouvrir le menu du back-office"}
              className="relative w-10 h-10 -ml-2 rounded-full flex items-center justify-center text-dark hover:bg-gray-100">
              <Menu size={22} aria-hidden />
              <Pastille nombre={enAttente} petite className="absolute top-0.5 left-0.5" />
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <Logo size="sm" />
              <span className="text-xs font-semibold text-muted truncate">
                · {courant?.label ?? "Back-office"}{sousPageCourante && ` · ${sousPageCourante.label}`}
              </span>
            </div>
          </div>
        </header>

        <MobileDrawer open={menuOuvert} onClose={() => setMenuOuvert(false)} label="Menu du back-office" side="left"
          header={<div><Logo size="sm" /><p className="text-[11px] font-bold uppercase tracking-widest text-muted mt-1">Back-office</p></div>}>
          <nav className="space-y-1" aria-label="Back-office">
            {menu.map(({ href, label, icon: Icon, compteur, sousPages }) => (
              <DrawerItem key={href}>
                <Link href={href} onClick={() => setMenuOuvert(false)} aria-current={!sousPages && actif(href) ? "page" : undefined}
                  className={cn("flex items-center gap-3 px-3 py-3 rounded-xl text-[15px] font-medium transition-colors", actif(href) ? "bg-primary/10 text-brand dark:bg-gray-100 dark:text-dark" : "text-dark hover:bg-gray-50")}>
                  <Icon size={18} /> {label}
                  {compteur && <Pastille nombre={enAttente} className="ml-auto" />}
                </Link>
                {/* On a phone the pages always show: the panel is the only way to reach them */}
                {sousPages && (
                  <ul className="mt-1 ml-[1.375rem] pl-3 border-l border-gray-100 space-y-0.5">
                    {sousPages.map((p) => (
                      <li key={p.href}>
                        <Link href={p.href} onClick={() => setMenuOuvert(false)} aria-current={actifSousPage(href, p.href) ? "page" : undefined}
                          className={cn("block px-3 py-2.5 rounded-lg text-[15px]", actifSousPage(href, p.href) ? "font-semibold text-brand dark:text-dark bg-gray-50" : "text-muted hover:text-dark hover:bg-gray-50")}>
                          {p.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </DrawerItem>
            ))}
          </nav>
          <DrawerItem className="mt-4 pt-4 border-t border-gray-100">
            <ThemeSelector full className="mx-3 mb-3" />
            <p className="text-xs text-muted truncate px-3">{session.user.email}</p>
            <Link href="/" className="mt-2 flex items-center gap-3 px-3 py-3 rounded-xl text-[15px] font-medium text-dark hover:bg-gray-50"><ArrowLeft size={18} /> Retour au site</Link>
          </DrawerItem>
        </MobileDrawer>
        <main id="contenu" tabIndex={-1} className="p-4 sm:p-6 lg:p-8 max-w-7xl outline-hidden">{children}</main>
        <AlerteVerifications compteurs={compteurs} />
      </div>
    </div>
  );
}

/** Number of pending items (hidden at 0). The `petite` variant sits on the mobile menu button. */
function Pastille({ nombre, petite, className }: { nombre: number; petite?: boolean; className?: string }) {
  if (nombre <= 0) return null;
  return (
    <span className={cn("rounded-full bg-orange-700 dark:bg-orange-600 text-white font-bold tabular-nums flex items-center justify-center",
      petite ? "min-w-[18px] h-[18px] px-1 text-[10px] ring-2 ring-surface" : "min-w-[22px] h-[22px] px-1.5 text-xs", className)}>
      {nombre > 99 ? "99+" : nombre}
      <span className="sr-only"> en attente</span>
    </span>
  );
}
