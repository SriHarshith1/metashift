import type { IndexFile, ReportFile } from "./types/generated";

const cache = new Map<string, Promise<unknown>>();

async function load<T>(path: string): Promise<T> {
  const url = `${import.meta.env.BASE_URL}data/${path}`;
  const fail = () => new Error(`could not load data/${path}`);
  try {
    const res = await fetch(url);
    if (!res.ok) throw fail();
    return (await res.json()) as T;
  } catch {
    throw fail();
  }
}

/** Fetch once per path. A failed fetch is dropped from the cache so a retry can succeed. */
function cached<T>(path: string): Promise<T> {
  let hit = cache.get(path) as Promise<T> | undefined;
  if (!hit) {
    hit = load<T>(path);
    hit.catch(() => cache.delete(path));
    cache.set(path, hit);
  }
  return hit;
}

export function fetchIndex(): Promise<IndexFile> {
  return cached<IndexFile>("index.json");
}

export function fetchReport(game: string, patch: string): Promise<ReportFile> {
  return cached<ReportFile>(`${game}/${patch}.json`);
}
