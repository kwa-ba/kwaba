"use client";

import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RotateCcw, Search } from "lucide-react";
import AdminTable, { ActionButton, Pagination, Pill, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import {
  agirSurRemboursement, lireApercuRemboursement, lireRemboursements, rembourserSejour,
  type ActionRemboursement, type BaremeRemboursement, type RemboursementAdmin, type StatutRemboursement,
} from "../api";
import { useConfigPaiement } from "../paiement";

const CHAMP = "px-3 py-2 border border-gray-200 rounded-xl bg-surface text-base sm:text-sm focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary";
// One cache key per read (documentation/frontieres-front.md)
const CLES = {
  liste: (statut: string, page: number) => ["admin", "paiements", "remboursements", statut, page] as const,
  apercu: (reference: string) => ["admin", "paiements", "remboursements", "apercu", reference] as const,
};
const TONS: Record<StatutRemboursement, "orange" | "bleu" | "vert" | "rouge" | "gris"> = {
  attente_numero: "orange", a_envoyer: "bleu", en_cours: "bleu", envoye: "vert", a_traiter: "rouge",
};
const FILTRES: [string, string][] = [["", "Tous"], ["a_traiter", "À traiter"], ["attente_numero", "Numéro attendu"],
  ["a_envoyer", "À envoyer"], ["en_cours", "En cours"], ["envoye", "Envoyés"]];

/**
 * Refunds (GL-9): refund a paid stay from its frozen amounts (never today's rates), under the traveller's terms or
 * in full, and follow every refund until it has left. From the threshold, a second person approves (Validations).
 */
export default function Remboursements() {
  return (
    <div className="space-y-6">
      <RembourserUnSejour />
      <ListeRemboursements />
    </div>
  );
}

function RembourserUnSejour() {
  const client = useQueryClient();
  const [saisie, setSaisie] = useState("");
  const [reference, setReference] = useState("");
  const [bareme, setBareme] = useState<BaremeRemboursement["code"] | "">("");
  const [motif, setMotif] = useState("");
  const apercu = useQuery({ queryKey: CLES.apercu(reference), queryFn: () => lireApercuRemboursement(reference), enabled: !!reference, retry: false });
  const rembourser = useMutation({
    mutationFn: () => rembourserSejour(apercu.data!.reservation.id, bareme as BaremeRemboursement["code"], motif.trim()),
    onSuccess: (r) => {
      if (r.attenteValidation) toast.info(r.message);
      else toast.success(r.message);
      setBareme("");
      setMotif("");
      client.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Remboursement impossible.")),
  });
  const choisi = apercu.data?.baremes.find((b) => b.code === bareme);

  return (
    <section className="bg-surface rounded-2xl border border-gray-100 p-5 space-y-4" aria-label="Rembourser un séjour">
      <div>
        <h2 className="font-heading font-bold text-dark">Rembourser un séjour</h2>
        <p className="text-sm text-muted">Le montant vient des tarifs figés au paiement. La réservation est annulée, l&apos;avoir est émis si elle était facturée.</p>
      </div>
      <form className="flex flex-col sm:flex-row gap-2" onSubmit={(e) => { e.preventDefault(); setReference(saisie.trim()); setBareme(""); }}>
        <input className={cn(CHAMP, "flex-1")} value={saisie} onChange={(e) => setSaisie(e.target.value)} placeholder="Référence (RES-AF2026-3A43) ou identifiant de la réservation" aria-label="Référence de la réservation" />
        <button type="submit" disabled={!saisie.trim()} className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 text-sm font-semibold disabled:opacity-50">
          <Search size={16} aria-hidden /> Chercher
        </button>
      </form>

      {apercu.isLoading && <div className="h-24 skeleton rounded-xl" />}
      {apercu.isError && <p role="alert" className="text-sm text-red-700">{apiErrorMessage(apercu.error, "Réservation introuvable.")}</p>}
      {apercu.data && (
        <div className="space-y-3">
          <p className="text-sm">
            <strong className="text-dark">{apercu.data.reservation.reference}</strong> · {apercu.data.reservation.voyageur} · du {formatDate(apercu.data.reservation.check_in)} au {formatDate(apercu.data.reservation.check_out)}
            {" "}· payé <strong className="tabular-nums">{formatPrice(apercu.data.paye)}</strong>
          </p>
          {apercu.data.validation_en_attente && <p className="text-sm bg-amber-50 text-amber-900 rounded-xl px-3 py-2">Un remboursement de ce séjour attend déjà une deuxième validation.</p>}
          {apercu.data.baremes.length === 0 ? (
            <p className="text-sm text-muted">{apercu.data.reservation.statut === "cancelled" ? "Réservation déjà annulée." : "Jamais payé en ligne : rien à rembourser."}</p>
          ) : (
            <>
              <fieldset className="grid sm:grid-cols-2 gap-2">
                <legend className="sr-only">Barème</legend>
                {apercu.data.baremes.map((b) => (
                  <label key={b.code} className={cn("rounded-xl border p-3 cursor-pointer text-sm", bareme === b.code ? "border-primary bg-primary/5" : "border-gray-200")}>
                    <input type="radio" name="bareme" className="sr-only" checked={bareme === b.code} onChange={() => setBareme(b.code)} />
                    <span className="block font-semibold text-dark">{b.libelle}</span>
                    <span className="block font-heading font-bold text-lg tabular-nums">{formatPrice(b.montant)}</span>
                    {b.validation_requise && <span className="block text-xs text-amber-800">À partir de {formatPrice(apercu.data!.seuil)} : une deuxième personne devra valider</span>}
                  </label>
                ))}
              </fieldset>
              <div className="flex flex-col sm:flex-row sm:items-end gap-2">
                <label className="text-sm flex-1"><span className="block text-xs font-semibold text-muted mb-1">Motif (obligatoire)</span>
                  <input className={cn(CHAMP, "w-full")} value={motif} onChange={(e) => setMotif(e.target.value)} maxLength={500} placeholder="Ex. logement indisponible, hôte injoignable" /></label>
                <button onClick={() => rembourser.mutate()} disabled={!bareme || motif.trim().length < 5 || rembourser.isPending || apercu.data.validation_en_attente}
                  className="px-4 py-2.5 rounded-xl bg-red-700 text-white text-sm font-bold disabled:opacity-50">
                  {rembourser.isPending ? "Envoi…" : choisi?.validation_requise ? "Demander la validation" : "Annuler et rembourser"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function ListeRemboursements() {
  const [statut, setStatut] = useState("");
  const [page, setPage] = useState(1);
  const [compte, setCompte] = useState<RemboursementAdmin | null>(null);
  const client = useQueryClient();
  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: CLES.liste(statut, page), queryFn: () => lireRemboursements(statut, page), placeholderData: keepPreviousData,
  });
  const agir = useMutation({
    mutationFn: ({ r, action, corps }: { r: RemboursementAdmin; action: ActionRemboursement; corps?: Record<string, string> }) =>
      agirSurRemboursement(r.id, action, corps),
    onSuccess: () => { toast.success("Remboursement mis à jour"); setCompte(null); client.invalidateQueries({ queryKey: ["admin"] }); },
    onError: (err) => toast.error(apiErrorMessage(err, "Action impossible.")),
  });

  const manuel = (r: RemboursementAdmin) => {
    const reference = window.prompt(`Remboursement de ${formatPrice(r.montant)} fait depuis le tableau de bord FedaPay : sa référence ?`);
    if (reference?.trim()) agir.mutate({ r, action: "manuel", corps: { reference: reference.trim() } });
  };

  const colonnes: Colonne<RemboursementAdmin>[] = [
    { titre: "Date", cellule: (r) => <span className="whitespace-nowrap">{formatDate(r.cree_le)}</span> },
    { titre: "Réservation", cellule: (r) => <span className="whitespace-nowrap">{r.reference}</span>, masquerMobile: true },
    { titre: "Payeur", cellule: (r) => r.payeur || "—" },
    { titre: "Motif", cellule: (r) => <span className="text-muted">{r.motif}</span> },
    { titre: "Statut", cellule: (r) => (
      <span><Pill ton={TONS[r.statut]}>{r.statut_libelle}</Pill>
        {r.derniere_erreur && <span className="block text-xs text-red-700 mt-1 max-w-64">{r.derniere_erreur}</span>}</span>
    ) },
    { titre: "Montant", cellule: (r) => <strong className="tabular-nums whitespace-nowrap">{formatPrice(r.montant)}</strong>, className: "text-right" },
  ];

  return (
    <section className="space-y-3" aria-label="Remboursements">
      <div className="flex flex-wrap gap-2">
        {FILTRES.map(([code, libelle]) => (
          <button key={code} onClick={() => { setStatut(code); setPage(1); }} aria-pressed={statut === code}
            className={cn("px-3 py-1.5 rounded-lg text-sm font-semibold border", statut === code ? "border-primary text-brand bg-primary/5" : "border-gray-200 text-dark hover:bg-gray-50")}>
            {libelle}
          </button>
        ))}
      </div>
      <AdminTable colonnes={colonnes} lignes={data?.results} cle={(r) => r.id} chargement={isLoading || isFetching} erreur={isError}
        onReessayer={() => refetch()} titreMobile={(r) => <span className="flex justify-between gap-2">{r.reference}<span className="tabular-nums">{formatPrice(r.montant)}</span></span>}
        actions={(r) => (
          <>
            {r.actions.includes("numero") && <ActionButton onClick={() => setCompte(r)}>Saisir le numéro</ActionButton>}
            {r.actions.includes("relancer") && <ActionButton onClick={() => agir.mutate({ r, action: "relancer" })}><RotateCcw size={12} className="inline" aria-hidden /> Relancer</ActionButton>}
            {r.actions.includes("manuel") && <ActionButton onClick={() => manuel(r)}>Fait manuellement</ActionButton>}
          </>
        )} />
      {data && <Pagination page={page} count={data.count} pageSize={data.page_size} onChange={setPage} />}
      {compte && <CompteMobileMoney r={compte} envoi={agir.isPending} onFermer={() => setCompte(null)}
        onValider={(corps) => agir.mutate({ r: compte, action: "numero", corps })} />}
    </section>
  );
}

/** The traveller's Mobile Money account, given by phone or email, entered by the team. */
function CompteMobileMoney({ r, envoi, onFermer, onValider }: {
  r: RemboursementAdmin; envoi: boolean; onFermer: () => void; onValider: (corps: Record<string, string>) => void;
}) {
  const { data: config } = useConfigPaiement();
  const [pays, setPays] = useState("TG");
  const [operateur, setOperateur] = useState("");
  const [numero, setNumero] = useState("");
  const operateurs = config?.pays.find((p) => p.code === pays)?.operateurs ?? [];
  const choisi = operateurs.some((o) => o.code === operateur) ? operateur : operateurs[0]?.code ?? "";

  return (
    <div className="bg-surface rounded-2xl border border-primary/30 p-4 space-y-3" role="dialog" aria-label="Compte Mobile Money">
      <p className="text-sm"><strong>{r.reference}</strong> · {formatPrice(r.montant)} à rembourser à {r.payeur || "voyageur"}</p>
      <div className="grid sm:grid-cols-3 gap-2">
        <select className={CHAMP} value={pays} onChange={(e) => setPays(e.target.value)} aria-label="Pays">
          {(config?.pays ?? []).map((p) => <option key={p.code} value={p.code}>{p.nom}</option>)}
        </select>
        <select className={CHAMP} value={choisi} onChange={(e) => setOperateur(e.target.value)} aria-label="Opérateur">
          {operateurs.map((o) => <option key={o.code} value={o.code}>{o.nom}</option>)}
        </select>
        <input className={CHAMP} value={numero} onChange={(e) => setNumero(e.target.value.replace(/\D/g, ""))} inputMode="numeric" placeholder="Numéro" aria-label="Numéro" />
      </div>
      <div className="flex gap-2">
        <button onClick={() => onValider({ pays, operateur: choisi, numero })} disabled={!choisi || numero.length < 8 || envoi}
          className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-bold disabled:opacity-50">Enregistrer et envoyer</button>
        <button onClick={onFermer} className="px-4 py-2 rounded-xl border border-gray-200 text-sm font-semibold">Annuler</button>
      </div>
    </div>
  );
}
