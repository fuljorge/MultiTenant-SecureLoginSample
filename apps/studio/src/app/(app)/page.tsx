"use client";

import { useMe } from "@cap/api-client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { activeOrganizationName } from "@/lib/auth/session";

export default function Home() {
  const me = useMe().data;
  if (!me) return null;

  if (me.kind === "super_admin") {
    return (
      <>
        <h1 className="text-2xl font-medium">Olá, {me.name}</h1>
        <Card className="corner-cut">
          <CardHeader>
            <CardTitle>Super Administrador</CardTitle>
            <CardDescription>
              Você gerencia as organizações desta instalação, os seus Administradores e o billing.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-muted-foreground">
            Você não tem acesso aos usuários nem aos dados de dentro das organizações.
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <h1 className="text-2xl font-medium">Olá, {me.name}</h1>
      <Card className="corner-cut">
        <CardHeader>
          <CardTitle>SecureLogin</CardTitle>
          <CardDescription>
            Você está na organização {activeOrganizationName(me) ?? "—"}.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-muted-foreground">
          Os módulos de agentes, conhecimento e integrações aparecem aqui conforme forem liberados
          para o seu perfil.
        </CardContent>
      </Card>
    </>
  );
}
