/** Which screen is showing, as a stack: games, then a game's commentators,
 * then listening. Android's back button goes back a step. */

import type { SportsEvent, Stream } from "@commentary-sync/client/schema";
import { useCallback, useEffect, useState } from "react";
import { BackHandler } from "react-native";

export type Route =
  | { name: "games" }
  | { name: "commentators"; game: SportsEvent }
  | { name: "listen"; game: SportsEvent; stream: Stream };

export interface Routes {
  current: Route;
  open(route: Route): void;
  back(): void;
}

const HOME: Route = { name: "games" };

export function useRoutes(): Routes {
  const [stack, setStack] = useState<Route[]>([HOME]);
  const open = useCallback((route: Route) => setStack((routes) => [...routes, route]), []);
  const back = useCallback(() => setStack((routes) => (routes.length > 1 ? routes.slice(0, -1) : routes)), []);
  const canGoBack = stack.length > 1;

  useEffect(() => {
    if (!canGoBack) return; // on the first screen, back leaves the app as usual
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      back();
      return true;
    });
    return () => subscription.remove();
  }, [back, canGoBack]);

  return { current: stack.at(-1) ?? HOME, open, back };
}
