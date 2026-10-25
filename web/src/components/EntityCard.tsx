import { useId, useState } from "react";
import { formatChange, formatPrevious } from "../format";
import type { Change, EntityVerdict } from "../types/generated";
import { VERDICT_BY_KIND } from "../verdict";

type Props = {
  verdict: EntityVerdict;
  changes: Change[];
  /** Game slug for the history link. v1 ships League of Legends only. */
  game?: string;
};

const DIRECTION_MARK = { buff: "▲", nerf: "▼", adjust: "●" } as const;

export default function EntityCard({ verdict, changes, game = "lol" }: Props) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const v = VERDICT_BY_KIND[verdict.verdict];
  const href = `#/${encodeURIComponent(game)}/${encodeURIComponent(verdict.entity_type)}/${encodeURIComponent(verdict.entity)}`;

  return (
    <article className="card" data-verdict={verdict.verdict}>
      <div className="card-head">
        {verdict.icon_url && <img className="card-icon" src={verdict.icon_url} alt="" width={48} height={48} loading="lazy" />}
        <div className="card-title">
          <h3>
            <a href={href}>{verdict.entity}</a>
          </h3>
          <p className="card-sub">
            <span className="verdict-badge">
              <span aria-hidden="true">{v.mark}</span> {v.label}
            </span>
            <span className="card-type">{verdict.entity_type}</span>
          </p>
        </div>
      </div>
      <dl className="card-facts">
        <div>
          <dt>Previous patch</dt>
          <dd>{formatPrevious(verdict.previous)}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd className="confidence" data-level={verdict.confidence}>
            {verdict.confidence} confidence
          </dd>
        </div>
      </dl>
      <p className="card-reason">{verdict.reason}</p>
      {verdict.impact && (
        <p className="card-note">
          <span className="card-note-label">Impact</span> {verdict.impact}
        </p>
      )}
      {verdict.build_shift && (
        <p className="card-note" data-kind="build">
          <span className="card-note-label">Build shift</span> {verdict.build_shift}
        </p>
      )}
      {changes.length > 0 && (
        <>
          <button type="button" className="card-toggle" aria-expanded={open} aria-controls={listId} onClick={() => setOpen(!open)}>
            {open ? "Hide changes" : "Show changes"} ({changes.length})
          </button>
          {open && (
            <ul className="change-list" id={listId}>
              {changes.map((c, i) => (
                <li key={i} data-direction={c.direction}>
                  <p className="change-what">
                    <span className="change-target">{c.target}</span>
                    <span className="change-stat">{c.stat}</span>
                  </p>
                  <p className="change-values">
                    <span aria-hidden="true">{DIRECTION_MARK[c.direction]}</span> {formatChange(c.old, c.new)}
                    <span className="visually-hidden"> ({c.direction})</span>
                  </p>
                  <blockquote>{c.source_quote}</blockquote>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  );
}
