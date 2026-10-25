import type { EntityVerdict } from "./types/generated";

export type VerdictKind = EntityVerdict["verdict"];

/** Display data per verdict. The mark carries the meaning too, so color is never the only cue. */
export const VERDICTS: { kind: VerdictKind; label: string; mark: string }[] = [
  { kind: "rise", label: "Rise", mark: "▲" },
  { kind: "stable", label: "Stable", mark: "●" },
  { kind: "fall", label: "Fall", mark: "▼" },
];

export const VERDICT_BY_KIND = Object.fromEntries(VERDICTS.map((v) => [v.kind, v])) as Record<VerdictKind, (typeof VERDICTS)[number]>;
