import { Link, useParams } from "react-router-dom";
import { LoadError, Loading } from "../components/Status";
import { fetchIndex } from "../data";
import { comparePatchesDesc } from "../format";
import { useLoad } from "../useLoad";

export default function PatchList() {
  const { game = "" } = useParams();
  const { data, error } = useLoad(fetchIndex, "index");
  if (error) return <LoadError message={error} />;
  if (!data) return <Loading what="patches" />;

  const entries = [...(data.games[game] ?? [])].sort((a, b) => comparePatchesDesc(a.patch, b.patch));
  if (entries.length === 0) return <p className="status">No patches published for {game} yet.</p>;

  return (
    <section>
      <h1 className="page-title">Patches</h1>
      <ul className="patch-list">
        {entries.map((e) => (
          <li key={e.patch} className="patch-row">
            <Link to={`/${encodeURIComponent(game)}/${encodeURIComponent(e.patch)}`} className="patch-link">
              <span className="patch-num">{e.patch}</span>
              <span className="patch-body">
                <span className="patch-headline">{e.headline}</span>
                <span className="patch-meta">
                  {e.patch_date && <time dateTime={e.patch_date}>{e.patch_date}</time>}
                  <span>{e.llm}</span>
                </span>
              </span>
              <span className="patch-counts">
                <span className="count-buff">▲ {e.buffs} buffs</span>
                <span className="count-nerf">▼ {e.nerfs} nerfs</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
