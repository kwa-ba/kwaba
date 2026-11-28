import { useQuery } from "@tanstack/react-query";
import { useLocale } from "next-intl";
import { listerGammes, listerGammesAdmin } from "./api";

export const clesMobilite = {
  tous: ["mobilite"],
  admin: ["admin", "mobilite"],
};

/** The ranges of the referential, in the language of the page (kept an hour: they rarely change). */
export function useGammes(usage?: "transfert" | "location") {
  const locale = useLocale();
  return useQuery({
    queryKey: [...clesMobilite.tous, "gammes", usage ?? "toutes", locale],
    queryFn: () => listerGammes(usage),
    staleTime: 60 * 60 * 1000,
  });
}

export function useGammesAdmin() {
  return useQuery({ queryKey: [...clesMobilite.admin, "gammes"], queryFn: listerGammesAdmin });
}
