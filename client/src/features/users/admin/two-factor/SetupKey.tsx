"use client";

import { Copy, ExternalLink } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import type { TwoFactorSetup } from "@/types/api/admin";
import { groupKey } from "./rules";

/** The three ways to add Kwa-Ba to the app: the link (phone), the QR code (computer), or the key typed by hand. */
export default function SetupKey({ setup }: { setup: TwoFactorSetup }) {
  const copier = async () => {
    try {
      await navigator.clipboard.writeText(setup.secret);
      toast.success("Clé copiée");
    } catch {
      toast.error("Copie impossible : sélectionnez la clé à la main.");
    }
  };

  return (
    <div className="space-y-4">
      <a href={setup.otpauth_uri}
        className="sm:hidden flex items-center justify-center gap-2 w-full px-4 py-3 rounded-xl bg-primary text-white text-sm font-bold hover:bg-primary-600">
        <ExternalLink size={16} aria-hidden /> Ouvrir dans l&apos;application
      </a>
      <div className="flex flex-col sm:flex-row gap-5 sm:items-center">
        {/* Always dark on white: an app cannot read a QR code inverted by the dark theme */}
        <div className="self-center sm:self-auto p-4 bg-white rounded-2xl border border-gray-200 shrink-0">
          <QRCodeSVG value={setup.otpauth_uri} size={144} marginSize={0} bgColor="#ffffff" fgColor="#111827"
            title="QR code à scanner avec l'application d'authentification" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold text-dark">Impossible de scanner ? Saisissez la clé</p>
          <div className="mt-2 flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-xl p-2 pl-3">
            <code className="flex-1 font-mono text-sm text-dark break-all select-all">{groupKey(setup.secret)}</code>
            <button type="button" onClick={copier}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-surface text-xs font-bold text-dark hover:bg-gray-50 shrink-0">
              <Copy size={14} aria-hidden /> Copier
            </button>
          </div>
          <p className="mt-2 text-xs text-muted">
            Choisissez « Saisir une clé de configuration » dans l&apos;application, type de clé : basé sur l&apos;heure.
          </p>
        </div>
      </div>
    </div>
  );
}
