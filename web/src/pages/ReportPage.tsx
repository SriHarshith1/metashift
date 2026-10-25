import { useParams } from "react-router-dom";
import Board from "../components/Board";
import Ripples from "../components/Ripples";
import { LoadError, Loading } from "../components/Status";
import WarningsPanel from "../components/WarningsPanel";
import { fetchReport } from "../data";
import { useLoad } from "../useLoad";

export default function ReportPage() {
  const { game = "", patch = "" } = useParams();
  const { data: report, error } = useLoad(() => fetchReport(game, patch), `${game}/${patch}`);
  if (error) return <LoadError message={error} />;
  if (!report) return <Loading what={`patch ${patch}`} />;

  return (
    <article>
      <header className="report-head">
        <h1 className="report-title">
          Patch {report.patch} · {report.compared_to ? `vs ${report.compared_to} meta` : "no previous patch"}
        </h1>
        <p className="report-headline">{report.headline}</p>
        {report.themes.length > 0 && (
          <ul className="chips" aria-label="Themes">
            {report.themes.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        )}
        <p className="report-meta">Written by {report.llm}</p>
      </header>
      <WarningsPanel warnings={report.warnings} />
      <Ripples game={game} ripples={report.ripples ?? []} />
      <Board report={report} />
    </article>
  );
}
