import { notFound } from "next/navigation";

/** Unknown back-office address: the back-office's own 404 page, in French. */
export default function AdresseInconnue() {
  notFound();
}
