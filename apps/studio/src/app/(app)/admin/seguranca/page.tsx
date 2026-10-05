"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  getReadSecuritySettingsQueryKey,
  useReadSecuritySettings,
  useUpdateSecuritySettings,
  type SecuritySettings,
} from "@cap/api-client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/labels";

type Field = { key: keyof SecuritySettings; label: string; min: number; max: number };

// Limites mínimos iguais aos da API (contracts/identity-api.md); a API valida de novo.
const GROUPS: { title: string; fields: Field[] }[] = [
  {
    title: "Senha",
    fields: [
      { key: "password_min_length", label: "Tamanho mínimo (caracteres)", min: 12, max: 128 },
      {
        key: "password_history",
        label: "Senhas anteriores que não podem ser reusadas",
        min: 0,
        max: 24,
      },
    ],
  },
  {
    title: "Sessão",
    fields: [
      {
        key: "session_idle_minutes",
        label: "Encerrar após inatividade (minutos)",
        min: 5,
        max: 480,
      },
      { key: "session_max_hours", label: "Duração máxima (horas)", min: 1, max: 24 },
    ],
  },
  {
    title: "Bloqueio por tentativas",
    fields: [
      { key: "lockout_failures", label: "Falhas seguidas até bloquear", min: 3, max: 10 },
      { key: "lockout_minutes", label: "Duração do bloqueio (minutos)", min: 1, max: 1440 },
    ],
  },
  {
    title: "Código enviado por e-mail",
    fields: [
      { key: "code_length", label: "Dígitos", min: 6, max: 10 },
      { key: "code_valid_minutes", label: "Validade (minutos)", min: 1, max: 15 },
      {
        key: "code_resend_minutes",
        label: "Intervalo mínimo entre reenvios (minutos)",
        min: 1,
        max: 60,
      },
    ],
  },
  {
    title: "Links enviados por e-mail",
    fields: [
      { key: "invitation_valid_hours", label: "Validade de convites (horas)", min: 1, max: 168 },
      {
        key: "recovery_link_minutes",
        label: "Validade da recuperação de senha (minutos)",
        min: 5,
        max: 120,
      },
    ],
  },
];

/** Configuração de segurança da instalação (RF-007, RF-010). */
export default function SecuritySettingsPage() {
  const queryClient = useQueryClient();
  const settings = useReadSecuritySettings();
  const [feedback, setFeedback] = useState<string | null>(null);
  const update = useUpdateSecuritySettings({
    mutation: {
      onSuccess: () => {
        setFeedback("Configuração salva.");
        queryClient.invalidateQueries({ queryKey: getReadSecuritySettingsQueryKey() });
      },
      onError: (error) => setFeedback(errorMessage(error)),
    },
  });

  if (settings.isPending) return <p className="text-muted-foreground">Carregando…</p>;
  if (settings.isError) return <p role="alert">{errorMessage(settings.error)}</p>;
  const current = settings.data;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const data = Object.fromEntries(
      GROUPS.flatMap((g) => g.fields).map((f) => [f.key, Number(form.get(f.key))]),
    ) as unknown as SecuritySettings;
    update.mutate({ data });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-medium">Segurança</h1>
        <p className="text-muted-foreground">
          Vale para todas as organizações da instalação. Os limites mínimos não podem ser
          afrouxados.
        </p>
      </div>
      {GROUPS.map((group) => (
        <Card key={group.title}>
          <CardHeader>
            <CardTitle>{group.title}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {group.fields.map((field) => (
              <div key={field.key} className="flex flex-col gap-2">
                <Label htmlFor={field.key}>{field.label}</Label>
                <Input
                  id={field.key}
                  name={field.key}
                  type="number"
                  required
                  min={field.min}
                  max={field.max}
                  defaultValue={current[field.key]}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
      {feedback && <p role="status">{feedback}</p>}
      <div>
        <Button type="submit" disabled={update.isPending}>
          Salvar
        </Button>
      </div>
    </form>
  );
}
