"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getGetOrganizationQueryKey,
  getListOrganizationsQueryKey,
  inviteAdministrator,
  renameOrganization,
  useCancelOrganization,
  useDisableAdministrator,
  useEnableAdministrator,
  useGetOrganization,
  useReactivateOrganization,
  useResendInvitation,
  useSuspendOrganization,
} from "@cap/api-client";

import { FormDialog } from "@/components/admin/form-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { errorMessage, ORGANIZATION_STATUS_LABELS, STATUS_LABELS } from "@/lib/labels";

/** Detalhe da organização para o Super Administrador (US5; RF-025 a RF-027). */
export default function OrganizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);
  const organization = useGetOrganization(id);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: getGetOrganizationQueryKey(id) });
    await queryClient.invalidateQueries({ queryKey: getListOrganizationsQueryKey() });
  }
  const handlers = (message: string) => ({
    mutation: {
      onSuccess: async () => {
        setFeedback(message);
        await refresh();
      },
      onError: (error: unknown) => setFeedback(errorMessage(error)),
    },
  });
  const suspend = useSuspendOrganization(handlers("Organização suspensa. Ninguém mais acessa."));
  const reactivate = useReactivateOrganization(handlers("Organização reativada."));
  const resend = useResendInvitation(handlers("Convite reenviado."));
  const cancel = useCancelOrganization(handlers("Organização cancelada."));
  const disable = useDisableAdministrator(handlers("Administrador desativado."));
  const enable = useEnableAdministrator(handlers("Administrador reativado."));

  if (organization.isPending) return <p className="text-muted-foreground">Carregando…</p>;
  if (organization.isError) return <p role="alert">{errorMessage(organization.error)}</p>;
  const org = organization.data;
  const busy = [suspend, reactivate, resend, cancel, disable, enable].some((m) => m.isPending);

  async function rename(values: Record<string, string>) {
    await renameOrganization(
      id,
      { name: values.name },
      { headers: { "If-Match": String(org.version) } },
    );
    await refresh();
    return "Organização renomeada.";
  }

  async function addAdministrator(values: Record<string, string>) {
    await inviteAdministrator(id, { name: values.name, email: values.email });
    await refresh();
    return `Convite enviado para ${values.email}.`;
  }

  return (
    <>
      <Link href="/admin/organizacoes" className="text-sm text-muted-foreground hover:underline">
        ← Organizações
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-medium">{org.name}</h1>
        <Badge variant={org.status === "active" ? "secondary" : "outline"}>
          {ORGANIZATION_STATUS_LABELS[org.status]}
        </Badge>
      </div>
      <p className="text-muted-foreground">Criada em {formatDateTime(org.created_at)}</p>

      <div className="flex flex-wrap gap-2">
        <FormDialog
          trigger="Renomear"
          title="Renomear organização"
          description="O novo nome aparece para todas as pessoas da organização."
          submitLabel="Salvar"
          fields={[{ name: "name", label: "Nome da organização", defaultValue: org.name }]}
          onSubmit={rename}
          variant="outline"
        />
        {org.status === "active" && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => suspend.mutate({ organizationId: id })}
          >
            Suspender
          </Button>
        )}
        {org.status === "suspended" && (
          <Button disabled={busy} onClick={() => reactivate.mutate({ organizationId: id })}>
            Reativar
          </Button>
        )}
        {org.status === "pending" && (
          <>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => resend.mutate({ organizationId: id })}
            >
              Reenviar convite
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => cancel.mutate({ organizationId: id })}
            >
              Cancelar organização
            </Button>
          </>
        )}
      </div>
      {feedback && <p role="status">{feedback}</p>}

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-lg font-medium">Administradores</h2>
          {org.status === "active" && (
            <FormDialog
              trigger="Convidar Administrador"
              title="Convidar Administrador"
              description="A pessoa recebe um link de uso único e passa a administrar esta organização."
              submitLabel="Enviar convite"
              fields={[
                { name: "name", label: "Nome" },
                { name: "email", label: "E-mail", type: "email" },
              ]}
              onSubmit={addAdministrator}
              variant="outline"
            />
          )}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>E-mail</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead className="sr-only">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {org.administrators.map((admin) => (
              <TableRow key={admin.id}>
                <TableCell>{admin.name}</TableCell>
                <TableCell className="break-all">{admin.email}</TableCell>
                <TableCell>
                  <Badge variant={admin.status === "active" ? "secondary" : "outline"}>
                    {STATUS_LABELS[admin.status] ?? admin.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  {admin.status === "active" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => disable.mutate({ organizationId: id, userId: admin.id })}
                    >
                      Desativar
                    </Button>
                  )}
                  {admin.status === "disabled" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => enable.mutate({ organizationId: id, userId: admin.id })}
                    >
                      Reativar
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </>
  );
}
