"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getListOrganizationsQueryKey,
  inviteOrganization,
  useListOrganizations,
  type ListOrganizationsOrgStatus,
} from "@cap/api-client";

import { FormDialog } from "@/components/admin/form-dialog";
import { Badge } from "@/components/ui/badge";
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
import { errorMessage, ORGANIZATION_STATUS_LABELS } from "@/lib/labels";

const ALL = "todas";

/** Organizações da instalação, para o Super Administrador (US5; RF-018, RF-025). */
export default function OrganizationsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>(ALL);
  const organizations = useListOrganizations({
    q: search || undefined,
    org_status: status === ALL ? undefined : (status as ListOrganizationsOrgStatus),
  });

  async function invite(values: Record<string, string>) {
    await inviteOrganization({
      name: values.name,
      admin_name: values.admin_name,
      admin_email: values.admin_email,
    });
    await queryClient.invalidateQueries({ queryKey: getListOrganizationsQueryKey() });
    return `Convite enviado para ${values.admin_email}. A organização fica pendente até a ativação.`;
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium">Organizações</h1>
          <p className="text-muted-foreground">
            Clientes desta instalação. Você vê os Administradores, não o conteúdo.
          </p>
        </div>
        <FormDialog
          trigger="Convidar organização"
          title="Convidar organização"
          description="O responsável recebe um link de uso único e vira o Administrador da organização."
          submitLabel="Enviar convite"
          fields={[
            { name: "name", label: "Nome da organização" },
            { name: "admin_name", label: "Nome do responsável" },
            { name: "admin_email", label: "E-mail do responsável", type: "email" },
          ]}
          onSubmit={invite}
        />
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          placeholder="Buscar por organização ou Administrador"
          aria-label="Buscar por organização ou Administrador"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label="Filtrar por situação" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todas as situações</SelectItem>
            {Object.entries(ORGANIZATION_STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {organizations.isError && <p role="alert">{errorMessage(organizations.error)}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Organização</TableHead>
            <TableHead>Situação</TableHead>
            <TableHead className="hidden md:table-cell">Administradores</TableHead>
            <TableHead className="hidden lg:table-cell">Criada em</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {organizations.data?.map((organization) => (
            <TableRow key={organization.id}>
              <TableCell>
                <Link
                  href={`/admin/organizacoes/${organization.id}`}
                  className="underline-offset-4 hover:underline"
                >
                  {organization.name}
                </Link>
              </TableCell>
              <TableCell>
                <Badge variant={organization.status === "active" ? "secondary" : "outline"}>
                  {ORGANIZATION_STATUS_LABELS[organization.status]}
                </Badge>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                {organization.administrators.map((a) => a.email).join(", ") || "—"}
              </TableCell>
              <TableCell className="hidden lg:table-cell">
                {formatDateTime(organization.created_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}
