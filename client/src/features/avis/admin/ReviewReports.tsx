"use client";

import { Flag } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { ActionButton } from "@/components/backoffice/AdminTable";
import type { AdminReviewReport } from "@/types/api/admin";

/** Pending reports of a review (ADR-040), with the decision to keep it: deleting it stays the page's own action. */
export default function ReviewReports({ reports, onDismiss }: { reports: AdminReviewReport[]; onDismiss: () => void }) {
  if (!reports.length) return null;
  return (
    <div className="mt-4 p-4 rounded-xl bg-amber-50 border border-amber-200">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-dark inline-flex items-center gap-2">
          <Flag size={14} className="text-amber-700" />
          {reports.length} signalement{reports.length > 1 ? "s" : ""} à traiter
        </p>
        <ActionButton onClick={onDismiss}>Classer sans suite</ActionButton>
      </div>
      <ul className="mt-2 space-y-1.5">
        {reports.map((report) => (
          <li key={report.id} className="text-sm text-gray-700">
            <span className="font-medium text-dark">{report.reason_label}</span>
            {report.details && <> : {report.details}</>}
            <span className="text-xs text-muted"> · {report.reporter.nom} ({report.reporter.email}) · {formatDate(report.created_at)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
