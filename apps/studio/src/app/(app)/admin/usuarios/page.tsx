"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getListInvitationsQueryKey,
  useListInvitations,
  useListUsers,
  useMe,
  useRevokeInvitation,
  type Profile,
} from "@cap/api-client";

import { InviteDialog } from "@/components/admin/invite-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { errorMessage, PROFILE_LABELS, PROFILES, STATUS_LABELS } from "@/lib/labels";

const ALL = "todos";

/** Usuários da organização ativa (US3 cenário 7). */
export default function UsersPage() {
  const me = useMe().data;
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [profile, setProfile] = useState<string>(ALL);
  const [status, setStatus] = useState<string>(ALL);

  const users = useListUsers({
    q: search || undefined,
    profile: profile === ALL ? undefined : (profile as Profile),
    user_status: status === ALL ? undefined : status,
  });
  const invitations = useListInvitations();
  const revoke = useRevokeInvitation({
    mutation: {
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getListInvitationsQueryKey() }),
    },
  });
  const canManage = me?.permissions.includes("users:manage") ?? false;

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium">Usuários</h1>
          <p className="text-muted-foreground">Pessoas com acesso à organização.</p>
        </div>
        {canManage && me?.active_organization_id && (
          <InviteDialog organizationId={me.active_organization_id} />
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          placeholder="Buscar por nome ou e-mail"
          aria-label="Buscar por nome ou e-mail"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={profile} onValueChange={setProfile}>
          <SelectTrigger aria-label="Filtrar por perfil" className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todos os perfis</SelectItem>
            {PROFILES.map((p) => (
              <SelectItem key={p} value={p}>
                {PROFILE_LABELS[p]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label="Filtrar por situação" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todas as situações</SelectItem>
            {["active", "invited", "disabled"].map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_LABELS[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {users.isError && <p role="alert">{errorMessage(users.error)}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead className="hidden md:table-cell">E-mail</TableHead>
            <TableHead>Perfil</TableHead>
            <TableHead>Situação</TableHead>
            <TableHead className="hidden lg:table-cell">Último acesso</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.data?.map((user) => {
            const membership = user.memberships.find(
              (m) => m.organization_id === me?.active_organization_id,
            );
            return (
              <TableRow key={user.id}>
                <TableCell>
                  <Link
                    href={`/admin/usuarios/${user.id}`}
                    className="underline-offset-4 hover:underline"
                  >
                    {user.name}
                  </Link>
                </TableCell>
                <TableCell className="hidden md:table-cell">{user.email}</TableCell>
                <TableCell>
                  {membership ? PROFILE_LABELS[membership.profile as Profile] : "—"}
                </TableCell>
                <TableCell>
                  <Badge variant={user.status === "active" ? "secondary" : "outline"}>
                    {STATUS_LABELS[user.status] ?? user.status}
                  </Badge>
                </TableCell>
                <TableCell className="hidden lg:table-cell">
                  {user.last_login_at ? formatDateTime(user.last_login_at) : "Nunca"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {!!invitations.data?.length && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-medium">Convites pendentes</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>E-mail</TableHead>
                <TableHead>Perfil</TableHead>
                <TableHead className="hidden sm:table-cell">Vale até</TableHead>
                <TableHead className="sr-only">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invitations.data.map((invitation) => (
                <TableRow key={invitation.id}>
                  <TableCell>{invitation.email}</TableCell>
                  <TableCell>{PROFILE_LABELS[invitation.profile as Profile]}</TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {formatDateTime(invitation.expires_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    {canManage && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={revoke.isPending}
                        onClick={() => revoke.mutate({ invitationId: invitation.id })}
                      >
                        Revogar
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}
    </>
  );
}
