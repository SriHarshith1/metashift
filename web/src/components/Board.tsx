import { useState, type KeyboardEvent } from "react";
import type { ReportFile } from "../types/generated";
import { VERDICTS, type VerdictKind } from "../verdict";
import EntityCard from "./EntityCard";
import Filters, { ALL_TYPES, type ConfidenceFilter } from "./Filters";

export default function Board({ report }: { report: ReportFile }) {
  const [entityType, setEntityType] = useState(ALL_TYPES);
  const [confidence, setConfidence] = useState<ConfidenceFilter>("all");
  const [tab, setTab] = useState<VerdictKind>("rise");

  const entityTypes = [...new Set(report.entities.map((e) => e.entity_type))];
  const visible = report.entities.filter(
    (e) => (entityType === ALL_TYPES || e.entity_type === entityType) && (confidence === "all" || e.confidence === confidence),
  );

  function onTabKey(e: KeyboardEvent, index: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = VERDICTS[(index + step + VERDICTS.length) % VERDICTS.length];
    setTab(next.kind);
    document.getElementById(`tab-${next.kind}`)?.focus();
  }

  return (
    <div className="board-wrap">
      <Filters
        entityTypes={entityTypes}
        entityType={entityType}
        confidence={confidence}
        onEntityType={setEntityType}
        onConfidence={setConfidence}
      />
      <div className="tabs" role="tablist" aria-label="Verdict">
        {VERDICTS.map((v, i) => (
          <button
            key={v.kind}
            id={`tab-${v.kind}`}
            type="button"
            role="tab"
            className="tab"
            data-verdict={v.kind}
            aria-selected={tab === v.kind}
            aria-controls={`col-${v.kind}`}
            tabIndex={tab === v.kind ? 0 : -1}
            onClick={() => setTab(v.kind)}
            onKeyDown={(e) => onTabKey(e, i)}
          >
            <span aria-hidden="true">{v.mark}</span>
            {` ${v.label} `}
            <span className="tab-count">{visible.filter((e) => e.verdict === v.kind).length}</span>
          </button>
        ))}
      </div>
      <div className="board">
        {VERDICTS.map((v) => {
          const items = visible.filter((e) => e.verdict === v.kind);
          return (
            <section key={v.kind} id={`col-${v.kind}`} className="column" data-verdict={v.kind} data-active={tab === v.kind} aria-labelledby={`head-${v.kind}`}>
              <h2 id={`head-${v.kind}`} className="column-head">
                <span aria-hidden="true">{v.mark}</span> {v.label} ({items.length})
              </h2>
              {items.length === 0 ? (
                <p className="column-empty">No {v.label.toLowerCase()} verdicts match these filters.</p>
              ) : (
                items.map((e) => (
                  <EntityCard
                    key={`${e.entity_type}/${e.entity}`}
                    game={report.game}
                    verdict={e}
                    changes={e.change_refs.map((i) => report.changes[i]).filter((c) => c !== undefined)}
                  />
                ))
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
