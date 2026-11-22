"use client";

import { useEffect } from "react";
import Link from "next/link";
import { appLink } from "./appReturn";

/** Page reached after a payment started in the mobile app: opens the app, with a button if the browser blocks it. */
export default function AppReturn({ scheme, path, query }: { scheme: string; path: string[]; query: string }) {
  const link = appLink(scheme, path, query);

  useEffect(() => {
    if (link) window.location.replace(link);
  }, [link]);

  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-background">
      <div className="max-w-sm text-center space-y-4">
        <h1 className="font-heading font-bold text-xl text-dark">Retour à l&apos;application Kwa-Ba</h1>
        {link ? (
          <>
            <p className="text-sm text-gray-600">Le résultat de votre paiement s&apos;affiche dans l&apos;application.</p>
            <a href={link} className="inline-block px-6 py-3 rounded-xl bg-primary text-white font-medium">Revenir à l&apos;application</a>
          </>
        ) : (
          <Link href="/" className="inline-block px-6 py-3 rounded-xl bg-primary text-white font-medium">Aller sur Kwa-Ba</Link>
        )}
      </div>
    </main>
  );
}
