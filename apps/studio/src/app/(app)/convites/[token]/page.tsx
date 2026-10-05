"use client";

import { useParams } from "next/navigation";

import { useAcceptInvitation } from "@cap/api-client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/labels";

/** Aceite de convite por pessoa já cadastrada (US3 cenário 1). Exige estar logado. */
export default function AcceptInvitationPage() {
  const { token } = useParams<{ token: string }>();
  const accept = useAcceptInvitation({
    // Recarga completa de propósito: /me e o menu passam a incluir a nova organização.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    mutation: { onSuccess: () => window.setTimeout(() => window.location.assign("/"), 1500) },
  });

  return (
    <Card className="corner-cut mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle>
          <h1>Convite para uma organização</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {accept.isSuccess ? (
          <p role="status">Convite aceito. Você agora faz parte da organização.</p>
        ) : (
          <>
            <p>Aceite para passar a atuar nesta organização com a sua conta.</p>
            {accept.isError && <p role="alert">{errorMessage(accept.error)}</p>}
            <Button onClick={() => accept.mutate({ token })} disabled={accept.isPending}>
              Aceitar convite
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
