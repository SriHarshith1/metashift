export function Loading({ what }: { what: string }) {
  return (
    <p className="status" role="status">
      Loading {what}…
    </p>
  );
}

export function LoadError({ message }: { message: string }) {
  return (
    <p className="status status-error" role="alert">
      {message}
    </p>
  );
}
