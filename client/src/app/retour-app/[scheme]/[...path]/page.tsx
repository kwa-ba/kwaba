import { AppReturn } from "@/features/paiements";

type Props = {
  params: Promise<{ scheme: string; path: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AppReturnPage({ params, searchParams }: Props) {
  const { scheme, path } = await params;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of [value ?? ""].flat()) query.append(key, item);
  }
  return <AppReturn scheme={scheme} path={path} query={query.toString()} />;
}
