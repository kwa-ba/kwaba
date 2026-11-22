import type { Metadata } from "next";
import Document, { metadataDuSite } from "@/components/layout/Document";

// Return from a payment to the mobile app (ADR-041): in French, never indexed
export async function generateMetadata(): Promise<Metadata> {
  return { ...(await metadataDuSite("fr")), title: "Retour à l'application · Kwa-Ba", robots: { index: false, follow: false } };
}

export default function AppReturnLayout({ children }: { children: React.ReactNode }) {
  return <Document locale="fr">{children}</Document>;
}
