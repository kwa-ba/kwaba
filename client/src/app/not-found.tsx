import Document from "@/components/layout/Document";
import PageIntrouvable from "@/components/layout/PageIntrouvable";

/**
 * Last resort for an address outside the site and the back-office (the root layout renders no <html>): the same
 * page, in French, the default language.
 */
export default function NotFound() {
  return (
    <Document locale="fr">
      <PageIntrouvable />
    </Document>
  );
}
