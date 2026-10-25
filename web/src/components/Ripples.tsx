import type { Ripple } from "../types/generated";

type Props = {
  ripples: Ripple[];
  game: string;
};

export default function Ripples({ ripples, game }: Props) {
  if (ripples.length === 0) return null;
  return (
    <section className="ripples" aria-labelledby="ripples-title">
      <h2 id="ripples-title">Ripple effects</h2>
      <p className="ripples-note">Indirect effects predicted from the changes and the official ability text. No win rates back them.</p>
      <ul className="ripple-list">
        {ripples.map((r) => (
          <li key={r.title} className="ripple">
            <h3>{r.title}</h3>
            <p>{r.explanation}</p>
            {r.entities.length > 0 && (
              <ul className="ripple-entities" aria-label={`Involved in ${r.title}`}>
                {r.entities.map((e) => (
                  <li key={e.entity}>
                    <a href={`#/${encodeURIComponent(game)}/${encodeURIComponent(e.entity_type)}/${encodeURIComponent(e.entity)}`}>
                      {e.icon_url && <img src={e.icon_url} alt="" width={24} height={24} loading="lazy" />}
                      {e.entity}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
