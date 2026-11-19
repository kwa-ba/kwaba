import PageIntrouvable from "@/components/layout/PageIntrouvable";

/** Back-office page that does not exist (/backoffice/finances/synthese, for example): in French, in the back-office frame. */
export default function NotFound() {
  return <PageIntrouvable espace="backoffice" />;
}
