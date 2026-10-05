import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Motivos enviados pelo Control Plane em /api/v1/auth/callback.
const MESSAGES: Record<string, string> = {
  cancelado: "O login foi cancelado.",
  expirado: "A tentativa de login expirou. Comece de novo.",
  falha: "Não foi possível concluir o login. Tente de novo.",
  "sem-acesso":
    "Sua conta não está ativa no SecureLogin. Procure o Administrador da sua organização.",
  "sem-organizacao":
    "Sua conta não está vinculada a nenhuma organização. Procure o Administrador da sua organização.",
};

export default async function LoginErrorPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { motivo } = await searchParams;
  const message = (typeof motivo === "string" && MESSAGES[motivo]) || MESSAGES.falha;

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <Card className="corner-cut w-full max-w-md">
        <CardHeader>
          <CardTitle>
            <h1>Não foi possível entrar</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p role="alert">{message}</p>
          <Button asChild>
            <a href="/api/v1/auth/login">Tentar de novo</a>
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
