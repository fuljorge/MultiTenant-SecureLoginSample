"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/auth/current-user";

/**
 * Mostra `children` só para quem tem `permission` na organização ativa; para os demais,
 * explica a falta de permissão em vez de exibir um erro genérico. As telas protegidas nem
 * chamam a API. A regra continua no servidor (RF-014): isto é só a interface.
 */
export function RequirePermission({
  permission,
  children,
}: {
  /** Uma permissão, ou várias das quais qualquer uma basta. */
  permission: string | string[];
  children: ReactNode;
}) {
  const me = useCurrentUser();
  const accepted = Array.isArray(permission) ? permission : [permission];

  if (accepted.some((p) => me.permissions.includes(p))) return <>{children}</>;

  return (
    <section className="flex flex-col items-start gap-3">
      <h1 className="text-2xl font-medium">Sem permissão</h1>
      <p className="text-muted-foreground">
        O seu perfil nesta organização não dá acesso a esta área. Se precisar dela, peça a um
        Administrador.
      </p>
      <Button variant="outline" asChild>
        <Link href="/">Voltar ao início</Link>
      </Button>
    </section>
  );
}
