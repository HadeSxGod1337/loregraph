import { createContext, useContext } from "react";

import type { PlaySession } from "../api/types";

const PlaySessionContext = createContext<PlaySession | null>(null);

export const PlaySessionProvider = PlaySessionContext.Provider;

/** The active player's session. Only valid inside PlayLayout, which
 * establishes it before rendering any child. */
export function usePlaySession(): PlaySession {
  const session = useContext(PlaySessionContext);
  if (session === null) {
    throw new Error("usePlaySession must be used within PlayLayout");
  }
  return session;
}
