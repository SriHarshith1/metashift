const DASH = "—";

/** "40 → 45". A missing side shows a dash, never the word null. */
export function formatChange(old: string | null, next: string | null): string {
  return `${old ?? DASH} → ${next ?? DASH}`;
}

/** "49.1%", or "no stats" when the stats source had no number. */
export function formatRate(v: number | null): string {
  return v === null ? "no stats" : `${v.toFixed(1)}%`;
}

/** Sort callback: newest patch first. Compares "26.9" and "26.21" by number. */
export function comparePatchesDesc(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pb[i] ?? 0) - (pa[i] ?? 0);
    if (diff !== 0 && !Number.isNaN(diff)) return diff;
  }
  return b.localeCompare(a);
}
