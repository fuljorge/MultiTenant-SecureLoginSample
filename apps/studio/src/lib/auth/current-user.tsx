"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { MeOut } from "@cap/api-client";

const CurrentUserContext = createContext<MeOut | null>(null);

/** Disponibiliza a pessoa logada (`/me`) para a área logada; o layout já a carregou. */
export function CurrentUserProvider({ me, children }: { me: MeOut; children: ReactNode }) {
  return <CurrentUserContext.Provider value={me}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser(): MeOut {
  const me = useContext(CurrentUserContext);
  if (!me) throw new Error("useCurrentUser fora de CurrentUserProvider");
  return me;
}
