"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  changeProfile,
  getGetUserQueryKey,
  getListUsersQueryKey,
  useDisableUser,
  useEnableUser,
  useGetUser,
  useMe,
  useRemoveMembership,
  useRequestEmailChange,
  useRevokeUserSessions,
  type MembershipOut,
  type Profile,
} from "@cap/api-client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatDateTime } from "@/lib/format";
import { errorMessage, PROFILE_LABELS, PROFILES, STATUS_LABELS } from "@/lib/labels";

/** Detalhe e ações sobre uma pessoa (US3 cenários 2 a 6). */
export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const me = useMe().data;
  const user = useGetUser(id);
  const [feedback, setFeedback] = useState<string | null>(null);

  const refresh = (message: string) => {
    setFeedback(message);
    queryClient.invalidateQueries({ queryKey: getGetUserQueryKey(id) });
    queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() });
  };
  const onError = (error: unknown) => setFeedback(errorMessage(error));

  const disable = useDisableUser({
    mutation: { onSuccess: () => refresh("Pessoa desativada."), onError },
  });
  const enable = useEnableUser({
    mutation: { onSuccess: () => refresh("Pessoa reativada."), onError },
  });
  const revokeSessions = useRevokeUserSessions({
    mutation: { onSuccess: () => refresh("Sessões encerradas."), onError },
  });
  const removeMembership = useRemoveMembership({
    mutation: { onSuccess: () => refresh("Pessoa removida da organização."), onError },
  });
  const requestEmailChange = useRequestEmailChange({
    mutation: {
      onSuccess: () => refresh("Enviamos um link de confirmação para o novo e-mail."),
      onError,
    },
  });
  // Chamada direta para enviar a versão lida (If-Match): edição concorrente responde 412.
  const updateProfile = useMutation({
    mutationFn: (m: { membership: MembershipOut; profile: Profile }) =>
      changeProfile(
        id,
        m.membership.organization_id,
        { profile: m.profile },
        { headers: { "If-Match": `"${m.membership.version}"` } },
      ),
    onSuccess: () => refresh("Perfil alterado. Vale a partir da próxima ação da pessoa."),
    onError,
  });

  if (user.isPending) return <p className="text-muted-foreground">Carregando…</p>;
  if (user.isError) return <p role="alert">Pessoa não encontrada.</p>;

  const person = user.data;
  const canManage = me?.permissions.includes("users:manage") ?? false;
  const isSelf = me?.id === person.id;

  function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("new_email"));
    requestEmailChange.mutate({ userId: id, data: { new_email: email } });
  }

  return (
    <>
      <Link href="/admin/usuarios" className="text-sm text-muted-foreground hover:underline">
        ← Usuários
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-medium">{person.name}</h1>
        <Badge variant={person.status === "active" ? "secondary" : "outline"}>
          {STATUS_LABELS[person.status] ?? person.status}
        </Badge>
        {person.blocked && <Badge variant="destructive">Bloqueado temporariamente</Badge>}
      </div>
      <p className="text-muted-foreground">
        {person.email} · Último acesso:{" "}
        {person.last_login_at ? formatDateTime(person.last_login_at) : "nunca"}
      </p>
      {feedback && <p role="status">{feedback}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Organizações e perfis</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {person.memberships.map((membership) => (
            <div key={membership.organization_id} className="flex flex-wrap items-center gap-3">
              <span className="min-w-40">{membership.organization_name}</span>
              <Select
                value={membership.profile}
                disabled={!canManage || updateProfile.isPending}
                onValueChange={(value) =>
                  updateProfile.mutate({ membership, profile: value as Profile })
                }
              >
                <SelectTrigger
                  aria-label={`Perfil em ${membership.organization_name}`}
                  className="w-64"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROFILES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {PROFILE_LABELS[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {membership.status === "pending" && <Badge variant="outline">Convite pendente</Badge>}
              {canManage && !isSelf && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    removeMembership.mutate({
                      userId: id,
                      organizationId: membership.organization_id,
                    })
                  }
                >
                  Remover da organização
                </Button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      {canManage && !isSelf && (
        <Card>
          <CardHeader>
            <CardTitle>Acesso</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="flex flex-wrap gap-3">
              {person.status === "disabled" ? (
                <Button onClick={() => enable.mutate({ userId: id })} disabled={enable.isPending}>
                  Reativar
                </Button>
              ) : (
                <Button
                  variant="destructive"
                  onClick={() => disable.mutate({ userId: id })}
                  disabled={disable.isPending}
                >
                  Desativar
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => revokeSessions.mutate({ userId: id })}
                disabled={revokeSessions.isPending}
              >
                Encerrar sessões
              </Button>
            </div>
            <form onSubmit={submitEmail} className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-email">Novo e-mail</Label>
                <Input id="new-email" name="new_email" type="email" required className="w-72" />
              </div>
              <Button type="submit" variant="outline" disabled={requestEmailChange.isPending}>
                Trocar e-mail
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </>
  );
}
