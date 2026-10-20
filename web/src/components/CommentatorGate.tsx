"use client";

/** Shows the studio to commentators, and the handle form to everyone else. */

import { type ReactNode, useCallback, useEffect, useState } from "react";

import HandleForm from "@/components/HandleForm";
import { useSession } from "@/hooks/useSession";
import * as api from "@/lib/api";
import { ApiError, HTTP_NOT_FOUND } from "@/lib/api";
import type { Commentator } from "@commentary-sync/client/schema";

type Profile = { state: "loading" } | { state: "none" } | { state: "ready"; commentator: Commentator } | { state: "failed"; detail: string };

export default function CommentatorGate({ children }: { children: (commentator: Commentator) => ReactNode }) {
  const { authorized } = useSession();
  const [profile, setProfile] = useState<Profile>({ state: "loading" });

  useEffect(() => {
    let isCurrent = true;
    authorized(api.myCommentatorProfile)
      .then((commentator) => isCurrent && setProfile({ state: "ready", commentator }))
      .catch((failure: unknown) => {
        if (!isCurrent) return;
        const isListener = failure instanceof ApiError && failure.status === HTTP_NOT_FOUND;
        const detail = failure instanceof ApiError ? failure.detail : "Couldn't load your profile.";
        setProfile(isListener ? { state: "none" } : { state: "failed", detail });
      });
    return () => {
      isCurrent = false;
    };
  }, [authorized]);

  const onCreated = useCallback((commentator: Commentator) => setProfile({ state: "ready", commentator }), []);

  if (profile.state === "loading") return <p className="card">Loading your profile…</p>;
  if (profile.state === "failed") return <p className="card" role="alert">{profile.detail}</p>;
  if (profile.state === "none") return <HandleForm onCreated={onCreated} />;
  return <>{children(profile.commentator)}</>;
}
