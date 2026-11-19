import { notFound } from "next/navigation";

/**
 * Any address that no page of the site serves: it ends up here (a catch-all comes after every other route) and
 * shows the site's own 404 page, in French or English, instead of Next.js' default English page.
 */
export default function AdresseInconnue() {
  notFound();
}
