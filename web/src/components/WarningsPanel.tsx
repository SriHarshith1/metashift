export default function WarningsPanel({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <details className="warnings">
      <summary>Warnings ({warnings.length})</summary>
      <ul>
        {warnings.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </details>
  );
}
