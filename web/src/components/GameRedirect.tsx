import { Navigate } from "react-router-dom";
import { fetchIndex } from "../data";
import { useLoad } from "../useLoad";
import { LoadError, Loading } from "./Status";

/** "/" sends the visitor to the first game listed in the index. */
export default function GameRedirect() {
  const { data, error } = useLoad(fetchIndex, "index");
  if (error) return <LoadError message={error} />;
  if (!data) return <Loading what="games" />;
  const first = Object.keys(data.games)[0];
  if (!first) return <p className="status">No games published yet.</p>;
  return <Navigate to={`/${encodeURIComponent(first)}`} replace />;
}
