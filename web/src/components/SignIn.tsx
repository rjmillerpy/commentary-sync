"use client";

/** Sign in, or create an account, with the API's own rules on each field. */

import { type FormEvent, useState } from "react";

import { useSession } from "@/hooks/useSession";
import { ApiError } from "@/lib/api";
import { MAX_DISPLAY_NAME_LENGTH, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@commentary-sync/client/schema";

type Mode = "sign-in" | "register";

const COPY: Record<Mode, { title: string; submit: string; switchTo: string }> = {
  "sign-in": { title: "Sign in to the studio", submit: "Sign in", switchTo: "Create an account instead" },
  register: { title: "Create your account", submit: "Create account", switchTo: "I already have an account" },
};

export default function SignIn() {
  const { signIn, register } = useSession();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const copy = COPY[mode];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    setIsBusy(true);
    setError(null);
    try {
      if (mode === "sign-in") await signIn(email, password);
      else await register({ email, password, display_name: String(form.get("display_name")) });
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : "Something went wrong; try again.");
      setIsBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} aria-labelledby="sign-in-title">
      <h2 id="sign-in-title">{copy.title}</h2>
      <Fields mode={mode} />
      {error !== null && <p role="alert">{error}</p>}
      <button type="submit" disabled={isBusy}>
        {copy.submit}
      </button>
      <button type="button" className="link" onClick={() => setMode(mode === "sign-in" ? "register" : "sign-in")}>
        {copy.switchTo}
      </button>
    </form>
  );
}

function Fields({ mode }: { mode: Mode }) {
  const isRegistering = mode === "register";
  return (
    <>
      {isRegistering && (
        <label>
          Display name
          <input name="display_name" required maxLength={MAX_DISPLAY_NAME_LENGTH} autoComplete="nickname" />
        </label>
      )}
      <label>
        Email
        <input name="email" type="email" required autoComplete="email" />
      </label>
      <label>
        Password
        <input
          name="password"
          type="password"
          required
          minLength={isRegistering ? MIN_PASSWORD_LENGTH : undefined}
          maxLength={MAX_PASSWORD_LENGTH}
          autoComplete={isRegistering ? "new-password" : "current-password"}
        />
      </label>
    </>
  );
}
