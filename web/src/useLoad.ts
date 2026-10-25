import { useEffect, useState } from "react";

export type LoadState<T> = { data: T | null; error: string | null };

/** Run an async loader when `key` changes. Returns the data, or the error message to show. */
export function useLoad<T>(load: () => Promise<T>, key: string): LoadState<T> {
  const [state, setState] = useState<LoadState<T> & { key: string }>({ data: null, error: null, key });
  useEffect(() => {
    let live = true;
    load().then(
      (data) => live && setState({ data, error: null, key }),
      (err: unknown) => live && setState({ data: null, error: err instanceof Error ? err.message : String(err), key }),
    );
    return () => {
      live = false;
    };
    // `load` is a fresh closure each render; `key` identifies what it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state.key === key ? state : { data: null, error: null };
}
