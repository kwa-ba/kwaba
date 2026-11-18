"use client";

import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Lock, LockOpen, TriangleAlert } from "lucide-react";
import { Pill } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import type { MoisComptable } from "../api";
import { useCloturerMois, useControlesCloture, useMoisComptables } from "../hooks";
import { CHAMP, ErreurLecture, libelleMois } from "./communs";

const ETATS = { ouverte: { libelle: "Ouvert", ton: "bleu" }, en_controle: { libelle: "En contrôle", ton: "orange" }, verrouillee: { libelle: "Clôturé", ton: "vert" } } as const;

/** « 2026-10-01 » → « 2026-10 » (address of the month) and « 10/2026 » (what to type to confirm). */
const cle = (mois: string) => mois.slice(0, 7);
const saisie = (mois: string) => `${mois.slice(5, 7)}/${mois.slice(0, 4)}`;

/**
 * Month closing (GL-7, FIN-08): the six checks of a month and, when they are all green, its locking. A locked month
 * receives no entry any more, whoever asks, and never opens again: the database refuses it. Months close in order,
 * once finished; only a super admin locks one.
 */
export default function Cloture() {
  const { data, isLoading, isError, error } = useMoisComptables();
  const [choisi, setChoisi] = useState<string | null>(null);
  const premierOuvert = data?.mois.filter((m) => !m.en_cours && m.etat !== "verrouillee").at(-1);
  const mois = choisi ?? (premierOuvert ? cle(premierOuvert.mois) : null);

  if (isLoading) return <div className="h-64 skeleton rounded-2xl" />;
  if (isError) return <ErreurLecture erreur={error} />;
  if (!data) return null;
  const courant = data.mois.find((m) => cle(m.mois) === mois);

  return (
    <div className="grid lg:grid-cols-[18rem_1fr] gap-5 items-start">
      <section className="bg-surface rounded-2xl border border-gray-100 p-3" aria-label="Mois comptables">
        <h2 className="font-heading font-bold text-dark px-2 pt-1 pb-2">Mois comptables</h2>
        <ul className="space-y-0.5">
          {data.mois.map((m) => (
            <li key={m.mois}>
              <button onClick={() => setChoisi(cle(m.mois))} aria-pressed={cle(m.mois) === mois}
                className={cn("w-full text-left px-2 py-2 rounded-lg text-sm flex items-center justify-between gap-2",
                  cle(m.mois) === mois ? "bg-primary/10 dark:bg-gray-100" : "hover:bg-gray-50")}>
                <span className="capitalize font-medium text-dark">{libelleMois(m.mois)}</span>
                {m.en_cours ? <Pill ton="gris">En cours</Pill> : <Pill ton={ETATS[m.etat].ton}>{ETATS[m.etat].libelle}</Pill>}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {courant ? <DetailMois mois={courant} peutVerrouiller={data.peut_verrouiller} premierOuvert={premierOuvert?.mois ?? null} />
        : <p className="bg-surface rounded-2xl border border-gray-100 p-8 text-center text-muted">Choisissez un mois.</p>}
    </div>
  );
}

function DetailMois({ mois, peutVerrouiller, premierOuvert }: { mois: MoisComptable; peutVerrouiller: boolean; premierOuvert: string | null }) {
  const { data, isLoading, isError, error } = useControlesCloture(cle(mois.mois));
  const cloturer = useCloturerMois();
  const [confirmation, setConfirmation] = useState("");
  const refuses = data?.controles.filter((c) => c.verdict !== "OK") ?? [];
  const verrouille = mois.etat === "verrouillee";
  const dansLOrdre = premierOuvert === mois.mois;

  const verrouiller = () => cloturer.mutate({ mois: cle(mois.mois), confirmation }, {
    onSuccess: () => { toast.success(`${libelleMois(mois.mois)} est clôturé.`); setConfirmation(""); },
    onError: (err) => toast.error(apiErrorMessage(err, "Clôture impossible.")),
  });

  return (
    <div className="space-y-4 min-w-0">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-heading font-bold text-xl text-dark capitalize">{libelleMois(mois.mois)}</h2>
        {verrouille
          ? <span className="flex items-center gap-1.5 text-sm text-emerald-800"><Lock size={16} aria-hidden /> Clôturé{mois.verrouillee_le && ` le ${formatDate(mois.verrouillee_le)}`}</span>
          : <span className="flex items-center gap-1.5 text-sm text-muted"><LockOpen size={16} aria-hidden /> {mois.en_cours ? "Mois en cours : il se clôturera une fois terminé" : "Ouvert"}</span>}
      </div>

      {isLoading && <div className="h-48 skeleton rounded-2xl" />}
      {isError && <ErreurLecture erreur={error} />}
      {data && (
        <section className={cn("rounded-2xl border p-5", refuses.length ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50")}>
          <h3 className="flex items-center gap-2 font-heading font-bold text-dark mb-3">
            {refuses.length ? <TriangleAlert size={20} className="text-red-700" aria-hidden /> : <CheckCircle2 size={20} className="text-emerald-700" aria-hidden />}
            {refuses.length ? `${refuses.length} contrôle${refuses.length > 1 ? "s" : ""} en échec` : "Les six contrôles sont verts"}
          </h3>
          <ul className="space-y-2 text-sm">
            {data.controles.map((c) => (
              <li key={c.controle} className={cn("rounded-xl px-3 py-2 bg-surface", c.verdict !== "OK" && "text-red-800")}>
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="font-semibold">{c.controle}</span>
                  <span className="tabular-nums">{c.verdict === "OK" ? "OK" : c.resultat}</span>
                </div>
                {c.verdict !== "OK" && <p className="text-xs mt-1">{c.que_faire}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!verrouille && !mois.en_cours && data && (
        <section className="bg-surface rounded-2xl border border-gray-100 p-5 space-y-3">
          <h3 className="font-heading font-bold text-dark">Verrouiller le mois</h3>
          <p className="text-sm text-muted">
            Définitif : plus aucune écriture ne pourra être passée dans ce mois, et il ne se rouvre jamais. Une erreur trouvée plus tard se
            corrige par une ligne inverse dans un mois ouvert.
          </p>
          {!peutVerrouiller ? <p className="text-sm text-dark">Seuls les super administrateurs verrouillent un mois.</p>
            : !dansLOrdre ? <p className="text-sm text-dark">Les mois se clôturent dans l&apos;ordre : clôturez d&apos;abord {premierOuvert ? libelleMois(premierOuvert) : "les mois précédents"}.</p>
              : refuses.length > 0 ? <p className="text-sm text-dark">Tous les contrôles doivent être verts.</p>
                : (
                  <div className="flex flex-col sm:flex-row sm:items-end gap-3">
                    <label className="text-sm"><span className="block text-xs font-semibold text-muted mb-1">Pour confirmer, saisissez {saisie(mois.mois)}</span>
                      <input className={CHAMP} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder={saisie(mois.mois)} inputMode="numeric" /></label>
                    <button onClick={verrouiller} disabled={confirmation.trim() !== saisie(mois.mois) || cloturer.isPending}
                      className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-red-700 text-white text-sm font-bold disabled:opacity-50">
                      <Lock size={16} aria-hidden /> {cloturer.isPending ? "Clôture…" : "Clôturer définitivement"}
                    </button>
                  </div>
                )}
        </section>
      )}
    </div>
  );
}
