"use client";

import { cn } from "@/lib/utils";
import { backupCodeInput, onlyDigits } from "./rules";

/** Code of the authenticator app (6 digits, numeric keyboard on a phone) or backup code (XXXX-XXXX). */
export default function CodeInput({ id, value, onChange, backup = false, invalid = false, disabled, autoFocus }: {
  id: string; value: string; onChange: (value: string) => void; backup?: boolean; invalid?: boolean;
  disabled?: boolean; autoFocus?: boolean;
}) {
  return (
    <input
      id={id} value={value} disabled={disabled} autoFocus={autoFocus}
      onChange={(e) => onChange(backup ? backupCodeInput(e.target.value) : onlyDigits(e.target.value))}
      inputMode={backup ? "text" : "numeric"} autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false}
      placeholder={backup ? "XXXX-XXXX" : "000000"} maxLength={backup ? 9 : 6} aria-invalid={invalid}
      className={cn(
        "w-full px-4 py-3 bg-surface border rounded-xl text-center font-mono text-2xl text-dark placeholder:text-gray-300",
        "focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:opacity-60",
        backup ? "tracking-[0.2em]" : "tracking-[0.5em]",
        invalid ? "border-red-400" : "border-gray-300",
      )}
    />
  );
}

export const isComplete = (code: string, backup: boolean) => (backup ? code.replace(/-/g, "").length === 8 : code.length === 6);
