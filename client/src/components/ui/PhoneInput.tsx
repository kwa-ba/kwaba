"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Globe, Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Floating from "@/components/ui/Floating";
import { usePopover } from "@/lib/usePopover";
import { cn } from "@/lib/utils";
import { type CodePays, PAYS_PAR_DEFAUT, type PaysTelephone } from "@/lib/telephone/countries";
import { DRAPEAUX } from "@/lib/telephone/drapeaux";
import {
  filtrerPays, lireTelephone, longueursAttendues, paysTelephone, type SaisieTelephone, verifierTelephone, versE164,
} from "@/lib/telephone/telephone";

type Langue = "fr" | "en";

const nomPays = (pays: PaysTelephone, langue: Langue) => (langue === "en" ? pays.nomEn : pays.nom);

/** Heights of the forms it sits in: back-office (py-2.5), site forms (py-3), host assistant (py-3.5). */
const TAILLES = {
  compact: { cadre: "rounded-xl", saisie: "py-2.5 text-base sm:text-sm" },
  normal: { cadre: "rounded-xl", saisie: "py-3 text-base sm:text-sm" },
  grand: { cadre: "rounded-2xl", saisie: "py-3.5 text-base" },
} as const;

/** Message of a number that cannot be sent, or null (empty or valid): forms call it before sending. */
export function useErreurTelephone() {
  const t = useTranslations("champTelephone");
  const langue: Langue = useLocale() === "en" ? "en" : "fr";
  return useCallback((valeur: string, pays: CodePays = PAYS_PAR_DEFAUT): string | null => {
    const erreur = verifierTelephone(valeur, pays);
    if (!erreur) return null;
    if (erreur.code === "international") return t("erreurInternational");
    const p = erreur.pays;
    return t("erreurLongueur", { pays: nomPays(p, langue), attendu: longueursAttendues(p, t("a")), indicatif: p.indicatif, exemple: p.exemple });
  }, [t, langue]);
}

/** SVG flag (emoji flags show as letters on Windows), or a globe for another dialling code. */
function Drapeau({ iso }: { iso: CodePays | null }) {
  if (!iso) return <Globe size={16} className="shrink-0 text-gray-400" aria-hidden />;
  return (
    <span
      aria-hidden
      className="block w-5 h-3.5 shrink-0 rounded-[2px] bg-cover bg-center ring-1 ring-black/5"
      style={{ backgroundImage: `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(DRAPEAUX[iso])}")` }}
    />
  );
}

interface PhoneInputProps {
  /** Number in E.164, or saved in an older format (« +228 90 00 00 00 »): it is read again. */
  value: string;
  /** Receives the number in E.164 (+22890123456), "" when empty. */
  onChange: (e164: string) => void;
  /** Label above the field; without it, the caller labels the field with `id`. */
  label?: React.ReactNode;
  labelClassName?: string;
  hint?: string;
  /** Error of the API or of the form; shown instead of the field's own check. */
  error?: string;
  id?: string;
  /** Name of a hidden field carrying the E.164, for a form sent without JavaScript. */
  name?: string;
  required?: boolean;
  disabled?: boolean;
  /** Country selected while the field is empty (Togo by default). */
  paysParDefaut?: CodePays;
  taille?: keyof typeof TAILLES;
  /** "tel" for the phone of the account, "off" for someone else's number (driver, renter). */
  autoComplete?: "tel" | "off";
  className?: string;
}

/**
 * Phone field of every form: country menu (flag, dialling code, arrow) on the left of the number, in one frame with
 * one focus ring. Gives the number in E.164; a number pasted with its code selects the country.
 */
export default function PhoneInput({
  value, onChange, label, labelClassName, hint, error, id, name, required, disabled = false,
  paysParDefaut = PAYS_PAR_DEFAUT, taille = "normal", autoComplete = "tel", className,
}: PhoneInputProps) {
  const t = useTranslations("champTelephone");
  const langue: Langue = useLocale() === "en" ? "en" : "fr";
  const erreurTelephone = useErreurTelephone();
  const { open, setOpen, ref, panelRef } = usePopover();
  const autoId = useId();
  const inputId = id ?? `tel-${autoId}`;
  const listId = `${inputId}-pays`;
  const boutonRef = useRef<HTMLButtonElement>(null);
  const saisieRef = useRef<HTMLInputElement>(null);
  const rechercheRef = useRef<HTMLInputElement>(null);

  const [saisie, setSaisie] = useState<SaisieTelephone>(() => lireTelephone(value, paysParDefaut));
  // Last value given or received: a new value from the form (reset, profile loaded) is read again
  const [suivie, setSuivie] = useState(value);
  const [touche, setTouche] = useState(false);
  const [recherche, setRecherche] = useState("");
  const [actif, setActif] = useState(0);

  if (value !== suivie) {
    setSuivie(value);
    if (value !== versE164(saisie)) setSaisie(lireTelephone(value, saisie.pays ?? paysParDefaut));
  }

  const pays = paysTelephone(saisie.pays);
  const e164 = versE164(saisie);
  // Own check once the field is left, so the message does not show while the number is being typed
  const message = error || (touche ? erreurTelephone(e164) : null) || undefined;
  // null: « Other dialling code », offered when nothing is searched
  const options: (PaysTelephone | null)[] = [...filtrerPays(recherche, langue), ...(recherche ? [] : [null])];
  const dims = TAILLES[taille];

  function changer(suivante: SaisieTelephone) {
    setSaisie(suivante);
    const valeur = versE164(suivante);
    setSuivie(valeur);
    onChange(valeur);
  }

  function changerTexte(texte: string) {
    const suivante = lireTelephone(texte, saisie.pays);
    // Another code fully erased: back to the default country
    changer(suivante.pays === null && !suivante.texte ? { pays: paysParDefaut, texte: "" } : suivante);
  }

  function ouvrir() {
    // The search starts empty: the active line is the selected country in the full list
    const toutes: (PaysTelephone | null)[] = [...filtrerPays("", langue), null];
    setRecherche("");
    setActif(Math.max(0, toutes.findIndex((o) => (o?.iso ?? null) === saisie.pays)));
    setOpen(true);
  }

  function fermer(retourBouton: boolean) {
    setOpen(false);
    if (retourBouton) boutonRef.current?.focus();
  }

  function choisir(choix: PaysTelephone | null) {
    if (!choix) changer({ pays: null, texte: "+" });
    // A number typed with another code does not belong to the chosen country
    else changer({ pays: choix.iso, texte: saisie.texte.startsWith("+") ? "" : saisie.texte });
    setOpen(false);
    requestAnimationFrame(() => saisieRef.current?.focus());
  }

  // Search focused on open with a mouse or keyboard; not on a touch screen, where the keyboard would hide the list
  useEffect(() => {
    if (open && !window.matchMedia("(pointer: coarse)").matches) rechercheRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open) document.getElementById(`${listId}-${actif}`)?.scrollIntoView({ block: "nearest" });
  }, [open, actif, listId]);

  const onKeyDownBouton = (e: React.KeyboardEvent) => {
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      ouvrir();
    }
  };

  const onKeyDownRecherche = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActif((i) => Math.min(options.length - 1, i + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActif((i) => Math.max(0, i - 1)); }
    if (e.key === "Enter") {
      e.preventDefault();
      if (options[actif] !== undefined) choisir(options[actif]);
    }
    if (e.key === "Escape") { e.preventDefault(); fermer(true); }
    if (e.key === "Tab") setOpen(false);
  };

  const libelleBouton = pays ? t("indicatif", { pays: nomPays(pays, langue), indicatif: pays.indicatif }) : t("indicatifLibre");
  const decrit = [message ? `${inputId}-error` : hint ? `${inputId}-hint` : null, pays ? null : `${inputId}-libre`]
    .filter(Boolean).join(" ") || undefined;

  return (
    <div className={className}>
      {label && (
        <label htmlFor={inputId} className={labelClassName ?? "block text-xs font-bold text-dark uppercase tracking-wide mb-2"}>
          {label}
        </label>
      )}
      <div
        ref={ref}
        className={cn(
          "flex items-stretch border transition-all",
          dims.cadre,
          disabled ? "bg-gray-50" : "bg-surface",
          message
            ? "border-red-300 focus-within:ring-2 focus-within:ring-red-100 focus-within:border-red-400"
            : "border-gray-200 focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary",
          open && !message && "border-primary ring-2 ring-primary/20",
        )}
      >
        <button
          ref={boutonRef}
          type="button"
          disabled={disabled}
          aria-label={libelleBouton}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          onClick={() => (open ? fermer(false) : ouvrir())}
          onKeyDown={onKeyDownBouton}
          className={cn(
            "flex items-center gap-1.5 pl-3 pr-2 shrink-0 text-dark outline-hidden transition-colors",
            dims.cadre, "rounded-r-none",
            "hover:bg-gray-50 focus-visible:bg-gray-100 disabled:cursor-not-allowed disabled:hover:bg-transparent",
          )}
        >
          <Drapeau iso={saisie.pays} />
          <span className="text-base sm:text-sm font-medium tabular-nums">{pays ? `+${pays.indicatif}` : "+"}</span>
          <ChevronDown size={14} aria-hidden className={cn("text-gray-400 transition-transform", open && "rotate-180")} />
        </button>
        <span aria-hidden className="w-px my-2 bg-gray-200 shrink-0" />
        <input
          ref={saisieRef}
          id={inputId}
          type="tel"
          inputMode="tel"
          autoComplete={autoComplete === "tel" ? "tel" : "off"}
          value={saisie.texte}
          onChange={(e) => changerTexte(e.target.value)}
          onBlur={() => setTouche(true)}
          placeholder={pays ? pays.exemple : t("exempleLibre")}
          required={required}
          disabled={disabled}
          maxLength={24}
          aria-invalid={!!message}
          aria-describedby={decrit}
          className={cn(
            "flex-1 min-w-0 pl-3 pr-4 bg-transparent text-dark placeholder:text-gray-400 outline-hidden disabled:text-gray-500 disabled:cursor-not-allowed",
            dims.saisie,
          )}
        />
        {name && <input type="hidden" name={name} value={e164} />}
      </div>
      {!pays && <span id={`${inputId}-libre`} className="sr-only">{t("autreIndicatifAide")}</span>}
      {message ? (
        <p id={`${inputId}-error`} className="text-xs text-red-600 mt-1.5 ml-1">{message}</p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-xs text-gray-400 mt-1.5 ml-1">{hint}</p>
      ) : null}

      {open && (
        <Floating ref={panelRef} anchor={ref} width={320} sheetOnMobile onClose={() => fermer(false)} label={t("choisirPays")} className="p-2 sm:max-h-96 flex flex-col">
          <p className="md:hidden font-heading font-bold text-dark text-lg px-2 pb-3">{t("choisirPays")}</p>
          <div className="relative mb-2 shrink-0">
            <Search size={15} aria-hidden className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              ref={rechercheRef}
              type="search"
              role="combobox"
              aria-label={t("rechercher")}
              aria-expanded
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={options.length ? `${listId}-${actif}` : undefined}
              value={recherche}
              onChange={(e) => { setRecherche(e.target.value); setActif(0); }}
              onKeyDown={onKeyDownRecherche}
              placeholder={t("rechercher")}
              autoComplete="off"
              className="w-full pl-9 pr-3 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-base sm:text-sm text-dark placeholder:text-gray-400 focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>
          <ul id={listId} role="listbox" aria-label={t("choisirPays")} className="overflow-y-auto overscroll-contain">
            {options.map((o, i) => {
              const choisi = (o?.iso ?? null) === saisie.pays;
              return (
                <li
                  key={o?.iso ?? "autre"} id={`${listId}-${i}`} role="option" aria-selected={choisi}
                  onClick={() => choisir(o)} onMouseEnter={() => setActif(i)}
                  className={cn(
                    "flex items-center gap-3 px-3 py-3 sm:py-2.5 rounded-xl cursor-pointer text-base sm:text-sm text-dark",
                    i === actif && "bg-gray-50", choisi && "font-semibold text-brand",
                  )}
                >
                  <Drapeau iso={o?.iso ?? null} />
                  <span className="flex-1 min-w-0 truncate">{o ? nomPays(o, langue) : t("autreIndicatif")}</span>
                  {o && <span className="text-gray-500 font-normal tabular-nums">+{o.indicatif}</span>}
                  <Check size={16} aria-hidden className={cn("shrink-0", choisi ? "opacity-100" : "opacity-0")} />
                </li>
              );
            })}
          </ul>
          {!options.length && <p className="px-3 py-6 text-center text-sm text-gray-500">{t("aucunPays")}</p>}
        </Floating>
      )}
    </div>
  );
}
