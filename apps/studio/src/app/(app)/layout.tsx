"use client";

import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-shell/app-header";
import { ReauthNotice } from "@/components/app-shell/reauth-notice";
import { Button } from "@/components/ui/button";
import { CurrentUserProvider } from "@/lib/auth/current-user";
import { useSession } from "@/lib/auth/session";

/** Área logada: exige sessão (sem ela, o hook redireciona ao login). */
export default function AppLayout({ children }: { children: ReactNode }) {
  const session = useSession();

  if (session.status === "loading") {
    return (
      <main className="flex flex-1 items-center justify-center p-6" aria-busy="true">
        <p className="text-muted-foreground">Carregando…</p>
      </main>
    );
  }

  if (session.status === "error") {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
        <p>Não foi possível carregar o SecureLogin.</p>
        <Button onClick={() => window.location.reload()}>Tentar de novo</Button>
      </main>
    );
  }

  return (
    <CurrentUserProvider me={session.me}>
      <AppHeader me={session.me} />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-4 sm:p-6">
        <ReauthNotice />
        {children}
      </main>
    </CurrentUserProvider>
  );
}
