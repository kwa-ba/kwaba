import { redirect } from "next/navigation";

// Former address: the ledger now sits in the Finance heading (GL-1)
export default function AncienGrandLivre() {
  redirect("/backoffice/finances/grand-livre");
}
