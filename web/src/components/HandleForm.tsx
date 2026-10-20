"use client";

/** Become a commentator: choose the permanent handle listeners find you by. */

import { type FormEvent, useState } from "react";

import { useSession } from "@/hooks/useSession";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { type Commentator, HANDLE_PATTERN, MAX_HANDLE_LENGTH, MIN_HANDLE_LENGTH } from "@commentary-sync/client/schema";

export default function HandleForm({ onCreated }: { onCreated: (commentator: Commentator) => void }) {
  const { authorized } = useSession();
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const handle = String(new FormData(event.currentTarget).get("handle"));
    setIsBusy(true);
    setError(null);
    try {
      onCreated(await authorized((token) => api.becomeCommentator(token, handle)));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : "Something went wrong; try again.");
      setIsBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} aria-labelledby="handle-title">
      <h2 id="handle-title">Pick your handle</h2>
      <p>Listeners find you by it. Letters, digits and underscores; it can&apos;t be changed later.</p>
      <label>
        Handle
        <input
          name="handle"
          required
          minLength={MIN_HANDLE_LENGTH}
          maxLength={MAX_HANDLE_LENGTH}
          pattern={HANDLE_PATTERN}
          autoComplete="username"
        />
      </label>
      {error !== null && <p role="alert">{error}</p>}
      <button type="submit" disabled={isBusy}>
        Become a commentator
      </button>
    </form>
  );
}
