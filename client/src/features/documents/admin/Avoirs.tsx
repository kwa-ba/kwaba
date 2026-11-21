"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, FileMinus } from "lucide-react";
import AdminTable, { ActionButton, Pagination, SearchInput, type Colonne } from "@/components/backoffice/AdminTable";
import { apiErrorMessage } from "@/lib/api";
import { messageErreurPdf } from "@/lib/documents";
import { formatDate, formatPrice } from "@/lib/utils";
import { PAGE_SIZE, useAdminList, useDebounced } from "@/lib/useAdminList";
import { emettreAvoir, lireFacturesARegulariser, telechargerAvoir, type AvoirAdmin } from "../api";

const CLE_A_REGULARISER = ["admin", "documents", "avoirs", "a-regulariser"] as const;

/**
 * Credit notes (GL-8): an invoice is never deleted nor changed; a sale given back (cancellation, refund) is neutralised
 * by a credit note of the series AVO that quotes it. They are issued by themselves at the refund; the invoices left
 * without one (issued before credit notes existed, company details missing at the time) are listed first.
 */
export default function Avoirs() {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const recherche = useDebounced(q);
  const { data, isLoading, isFetching, isError, refetch, page, setPage } = useAdminList<AvoirAdmin>("documents/avoirs", { q: recherche });
  const aRegler = useQuery({ queryKey: CLE_A_REGULARISER, queryFn: lireFacturesARegulariser });
  const emettre = useMutation({
    mutationFn: emettreAvoir,
    onSuccess: (a) => { toast.success(`Avoir ${a.numero} émis sur ${a.facture.numero}`); client.invalidateQueries({ queryKey: ["admin"] }); },
    onError: (err) => toast.error(apiErrorMessage(err, "Avoir impossible.")),
  });
  const telecharger = async (a: AvoirAdmin) => {
    try {
      await telechargerAvoir(a);
    } catch (err) {
      toast.error(await messageErreurPdf(err, "Téléchargement impossible."));
    }
  };

  const colonnes: Colonne<AvoirAdmin>[] = [
    { titre: "Numéro", cellule: (a) => <strong className="whitespace-nowrap">{a.numero}</strong>, masquerMobile: true },
    { titre: "Émis le", cellule: (a) => formatDate(a.emis_le) },
    { titre: "Facture", cellule: (a) => <span className="whitespace-nowrap">{a.facture.numero} <span className="text-muted">({formatPrice(a.facture.total_ttc)})</span></span> },
    { titre: "Client", cellule: (a) => a.facture.client_nom },
    { titre: "Motif", cellule: (a) => <span className="text-muted">{a.motif}</span> },
    { titre: "Montant", cellule: (a) => <strong className="tabular-nums whitespace-nowrap">− {formatPrice(a.total_ttc)}</strong>, className: "text-right" },
  ];

  return (
    <div className="space-y-5">
      {aRegler.data && aRegler.data.length > 0 ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 p-4 space-y-3" aria-label="Factures à régulariser">
          <h2 className="flex items-center gap-2 font-heading font-bold text-dark">
            <AlertTriangle size={18} className="text-red-700" aria-hidden />
            {aRegler.data.length} facture{aRegler.data.length > 1 ? "s" : ""} remboursée{aRegler.data.length > 1 ? "s" : ""} sans avoir
          </h2>
          <ul className="divide-y divide-red-100 text-sm">
            {aRegler.data.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span><strong>{f.numero}</strong> · {f.client_nom} · facture {formatPrice(f.total_ttc)}
                  <span className="text-muted"> · reste à neutraliser {formatPrice(f.a_neutraliser)}</span></span>
                <ActionButton onClick={() => emettre.mutate(f.id)} disabled={emettre.isPending}>Émettre l&apos;avoir</ActionButton>
              </li>
            ))}
          </ul>
        </section>
      ) : aRegler.data && (
        <p className="flex items-center gap-2 text-sm text-emerald-800"><CheckCircle2 size={16} aria-hidden /> Toute facture remboursée a son avoir.</p>
      )}

      <div className="flex gap-3"><SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Numéro d'avoir, de facture ou client" /></div>
      <AdminTable colonnes={colonnes} lignes={data?.results} cle={(a) => a.id} chargement={isLoading || isFetching} erreur={isError}
        onReessayer={() => refetch()} titreMobile={(a) => <span className="flex items-center gap-2"><FileMinus size={16} aria-hidden /> {a.numero}</span>}
        actions={(a) => <ActionButton onClick={() => telecharger(a)}>PDF</ActionButton>} />
      {data && <Pagination page={page} count={data.count} pageSize={PAGE_SIZE} onChange={setPage} />}
    </div>
  );
}
