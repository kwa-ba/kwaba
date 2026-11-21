"use client";

import { signOut } from "next-auth/react";
import { LogOut, User } from "lucide-react";
import Logo from "@/components/layout/Logo";
import { cn } from "@/lib/utils";

export function SignOutButton({ className }: { className?: string }) {
  return (
    <button type="button" onClick={() => signOut({ callbackUrl: "/" })}
      className={cn("inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 bg-surface text-sm font-bold text-dark hover:bg-gray-50", className)}>
      <LogOut size={16} aria-hidden /> Se déconnecter
    </button>
  );
}

/** Page of the second factor screens: header without the back-office menu, which stays hidden until verified. */
export default function TwoFactorFrame({ email, wide = false, children }: {
  /** Shown in the header (setup screen); without it, the header holds the sign-out button (code screen). */
  email?: string; wide?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <header className="bg-surface border-b border-gray-100 px-4 sm:px-8 py-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Logo size="sm" />
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted mt-1">Back-office</p>
        </div>
        {email ? (
          <p className="flex items-center gap-2 text-sm text-muted min-w-0">
            <User size={16} aria-hidden className="shrink-0" />
            <span className="truncate">Connecté en tant que <strong className="text-dark">{email}</strong></span>
          </p>
        ) : <SignOutButton />}
      </header>
      <main className={cn("flex-1 w-full mx-auto px-4 sm:px-6 py-8 sm:py-12", wide ? "max-w-5xl" : "max-w-md")}>{children}</main>
    </div>
  );
}
