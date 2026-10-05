"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getListSuperAdminsQueryKey,
  inviteSuperAdmin,
  useDisableSuperAdmin,
  useEnableSuperAdmin,
  useListSuperAdmins,
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
import { useCurrentUser } from "@/lib/auth/current-user";
import { formatDateTime } from "@/lib/format";
import { errorMessage, STATUS_LABELS } from "@/lib/labels";

/** Super Administradores da instalação (US5; RF-030). */
export default function SuperAdminsPage() {
  const me = useCurrentUser();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);
  const superAdmins = useListSuperAdmins();
  const refresh = () => queryClient.invalidateQueries({ queryKey: getListSuperAdminsQueryKey() });
  const handlers = (message: string) => ({
    mutation: {
      onSuccess: async () => {
        setFeedback(message);
        await refresh();
      },
      onError: (error: unknown) => setFeedback(errorMessage(error)),
    },
  });
  const disable = useDisableSuperAdmin(handlers("Super Administrador desativado."));
  const enable = useEnableSuperAdmin(handlers("Super Administrador reativado."));

  async function invite(values: Record<string, string>) {
    await inviteSuperAdmin({ name: values.name, email: values.email });
    await refresh();
    return `Convite enviado para ${values.email}.`;
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium">Super Administradores</h1>
          <p className="text-muted-foreground">
            Equipe do fornecedor que gerencia as organizações desta instalação.
          </p>
        </div>
        <FormDialog
          trigger="Convidar Super Administrador"
          title="Convidar Super Administrador"
          description="A pessoa recebe um link de uso único. Ela não pode ter vínculo com organizações."
          submitLabel="Enviar convite"
          fields={[
            { name: "name", label: "Nome" },
            { name: "email", label: "E-mail", type: "email" },
          ]}
          onSubmit={invite}
        />
      </div>
      {feedback && <p role="status">{feedback}</p>}
      {superAdmins.isError && <p role="alert">{errorMessage(superAdmins.error)}</p>}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead className="hidden md:table-cell">E-mail</TableHead>
            <TableHead>Situação</TableHead>
            <TableHead className="hidden lg:table-cell">Último acesso</TableHead>
            <TableHead className="sr-only">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {superAdmins.data?.map((person) => (
            <TableRow key={person.id}>
              <TableCell>{person.name}</TableCell>
              <TableCell className="hidden md:table-cell">{person.email}</TableCell>
              <TableCell>
                <Badge variant={person.status === "active" ? "secondary" : "outline"}>
                  {STATUS_LABELS[person.status] ?? person.status}
                </Badge>
              </TableCell>
              <TableCell className="hidden lg:table-cell">
                {person.last_login_at ? formatDateTime(person.last_login_at) : "Nunca"}
              </TableCell>
              <TableCell className="text-right">
                {person.id !== me.id && person.status === "active" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={disable.isPending}
                    onClick={() => disable.mutate({ userId: person.id })}
                  >
                    Desativar
                  </Button>
                )}
                {person.status === "disabled" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={enable.isPending}
                    onClick={() => enable.mutate({ userId: person.id })}
                  >
                    Reativar
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}
