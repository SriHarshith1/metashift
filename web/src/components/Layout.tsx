import { useEffect, useState } from "react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";
import { fetchIndex } from "../data";
import { useLoad } from "../useLoad";

export const DISCLAIMER =
  "Metashift isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.";

type Theme = "light" | "dark";
const STORAGE_KEY = "metashift-theme";

function systemTheme(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage blocked: fall through to the system theme */
  }
  return systemTheme();
}

export default function Layout() {
  const { game } = useParams();
  const navigate = useNavigate();
  const { data: index } = useLoad(fetchIndex, "index");
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const games = index ? Object.keys(index.games) : [];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage blocked: the choice lasts for this visit only */
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          Meta<span>shift</span>
        </Link>
        <div className="topbar-tools">
          {games.length > 0 && (
            <label className="game-switch">
              <span className="visually-hidden">Game</span>
              <select value={game ?? games[0]} onChange={(e) => navigate(`/${encodeURIComponent(e.target.value)}`)}>
                {games.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            {theme === "dark" ? "☀ Light" : "☾ Dark"}
          </button>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="footer">
        <p>{DISCLAIMER}</p>
      </footer>
    </div>
  );
}
