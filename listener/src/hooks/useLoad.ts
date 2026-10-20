/** Loads something once, and again on `reload`: a list for a screen. */

import { ApiError } from "@commentary-sync/client/api";
import { useCallback, useEffect, useState } from "react";

const GENERIC_FAILURE = "Something went wrong; try again.";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
  reload(): void;
}

export function useLoad<T>(load: () => Promise<T>): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let isCurrent = true; // a load that finishes after unmount or a newer load is dropped
    load()
      .then((loaded) => {
        if (!isCurrent) return;
        setData(loaded);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (isCurrent) setError(failure instanceof ApiError ? failure.detail : GENERIC_FAILURE);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [load, attempt]);

  const reload = useCallback(() => {
    setIsLoading(true);
    setAttempt((count) => count + 1);
  }, []);
  return { data, error, isLoading, reload };
}
