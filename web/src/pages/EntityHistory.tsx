import { Link, useParams } from "react-router-dom";
import { LoadError, Loading } from "../components/Status";
import { fetchIndex, fetchReport } from "../data";
import { comparePatchesDesc, formatChange, formatPrevious } from "../format";
import type { Change, EntityVerdict, ReportFile } from "../types/generated";
import { useLoad } from "../useLoad";
import { VERDICT_BY_KIND } from "../verdict";

type Row = { report: ReportFile; changes: Change[]; verdict: EntityVerdict | undefined };

async function loadRows(game: string, entityType: string, entity: string): Promise<Row[]> {
  const index = await fetchIndex();
  const patches = (index.games[game] ?? []).map((e) => e.patch).sort(comparePatchesDesc);
  const reports = await Promise.all(patches.map((p) => fetchReport(game, p)));
  const rows: Row[] = [];
  for (const report of reports) {
    const same = (x: { entity: string; entity_type: string }) => x.entity === entity && x.entity_type === entityType;
    const changes = report.changes.filter(same);
    if (changes.length > 0) rows.push({ report, changes, verdict: report.entities.find(same) });
  }
  return rows;
}

export default function EntityHistory() {
  const { game = "", entityType = "", entity = "" } = useParams();
  const { data: rows, error } = useLoad(() => loadRows(game, entityType, entity), `${game}/${entityType}/${entity}`);
  if (error) return <LoadError message={error} />;
  if (!rows) return <Loading what={`history of ${entity}`} />;

  return (
    <section>
      <p className="crumb">
        <Link to={`/${encodeURIComponent(game)}`}>All patches</Link>
      </p>
      <h1 className="page-title">{entity}</h1>
      <p className="history-sub">
        {entityType} · {game}
      </p>
      {rows.length === 0 ? (
        <p className="status">No published patch changed {entity}.</p>
      ) : (
        <ol className="history-list">
          {rows.map(({ report, changes, verdict }) => {
            const v = verdict ? VERDICT_BY_KIND[verdict.verdict] : undefined;
            return (
              <li key={report.patch} className="history-row" data-verdict={verdict?.verdict ?? "none"}>
                <Link className="history-patch" to={`/${encodeURIComponent(game)}/${encodeURIComponent(report.patch)}`}>
                  Patch {report.patch}
                </Link>
                <div className="history-changes">
                  {changes.map((c, i) => (
                    <p key={i} data-direction={c.direction}>
                      <span className="change-target">{c.target}</span> <span className="change-stat">{c.stat}</span>{" "}
                      <span className="change-values">{formatChange(c.old, c.new)}</span>
                    </p>
                  ))}
                </div>
                <div className="history-verdict">
                  {v && verdict ? (
                    <>
                      <span className="verdict-badge">
                        <span aria-hidden="true">{v.mark}</span> {v.label}
                      </span>
                      <span>{verdict.confidence} confidence</span>
                    </>
                  ) : (
                    <span>no verdict</span>
                  )}
                  <span className="history-prev">Previous patch: {formatPrevious(verdict?.previous)}</span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
