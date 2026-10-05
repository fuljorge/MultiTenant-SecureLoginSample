"use client";

import { useParams } from "next/navigation";

import { useConfirmEmailChange } from "@cap/api-client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/labels";

/**
 * Confirmação do novo e-mail (US3 cenário 6). Página pública: o link chega por e-mail.
 * A confirmação exige um clique, para que leitores de e-mail que abrem links sozinhos não
 * consumam o link de uso único.
 */
export default function ConfirmEmailPage() {
  const { token } = useParams<{ token: string }>();
  const confirm = useConfirmEmailChange();

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <Card className="corner-cut w-full max-w-md">
        <CardHeader>
          <CardTitle>
            <h1>Confirmar novo e-mail</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {confirm.isSuccess ? (
            <>
              <p role="status">
                E-mail confirmado. Por segurança, suas sessões foram encerradas: entre de novo com o
                novo e-mail.
              </p>
              <Button asChild>
                <a href="/api/v1/auth/login">Entrar</a>
              </Button>
            </>
          ) : (
            <>
              <p>Confirme para passar a usar este endereço na sua conta do SecureLogin.</p>
              {confirm.isError && <p role="alert">{errorMessage(confirm.error)}</p>}
              <Button onClick={() => confirm.mutate({ token })} disabled={confirm.isPending}>
                Confirmar e-mail
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
