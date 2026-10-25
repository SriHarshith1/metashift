export type ConfidenceFilter = "all" | "low" | "medium" | "high";

const CONFIDENCE_OPTIONS: { value: ConfidenceFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

type Props = {
  entityTypes: string[];
  entityType: string;
  confidence: ConfidenceFilter;
  onEntityType: (value: string) => void;
  onConfidence: (value: ConfidenceFilter) => void;
};

export const ALL_TYPES = "all";

export default function Filters({ entityTypes, entityType, confidence, onEntityType, onConfidence }: Props) {
  return (
    <div className="filters">
      <label>
        <span>Entity type</span>
        <select value={entityType} onChange={(e) => onEntityType(e.target.value)}>
          <option value={ALL_TYPES}>All types</option>
          {entityTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Confidence</span>
        <select value={confidence} onChange={(e) => onConfidence(e.target.value as ConfidenceFilter)}>
          {CONFIDENCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
