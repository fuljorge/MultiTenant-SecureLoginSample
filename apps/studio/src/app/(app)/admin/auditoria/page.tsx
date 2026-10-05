"use client";

import { useState } from "react";

import {
  capDownload,
  getExportAuditEventsUrl,
  useListAuditEvents,
  type AuditEventOut,
  type ListAuditEventsParams,
  type ListAuditEventsResult,
} from "@cap/api-client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { useCurrentUser } from "@/lib/auth/current-user";
import { isReauthRequired, redirectToReauth } from "@/lib/auth/reauth";
import { formatDateTime } from "@/lib/format";
import { AUDIT_EVENT_LABELS, AUDIT_RESULT_LABELS, errorMessage } from "@/lib/labels";

const ALL = "todos";
const PAGE = 50;

/** Data local (AAAA-MM-DD) para o início do dia em ISO; `nextDay` dá o limite exclusivo. */
function dayStart(value: string, nextDay = false): string | undefined {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00`);
  if (nextDay) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

function actorLabel(event: AuditEventOut): string {
  if (event.actor_name) return event.actor_name;
  if (event.actor_kind === "system") return "Sistema";
  if (event.actor_kind === "support") return "Suporte do fornecedor";
  if (event.installation_scope) return "Super Administrador";
  return "—";
}

/** Histórico de eventos de acesso (US6; RF-022, RF-023). O escopo vem da API. */
export default function AuditPage() {
  const me = useCurrentUser();
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState<string>(ALL);
  const [result, setResult] = useState<string>(ALL);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const filters: ListAuditEventsParams = {
    q: search.trim() || undefined,
    event_type: eventType === ALL ? undefined : eventType,
    result: result === ALL ? undefined : (result as ListAuditEventsResult),
    date_from: dayStart(from),
    date_to: dayStart(to, true),
  };
  const events = useListAuditEvents({ ...filters, limit: PAGE, offset: page * PAGE });

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await capDownload(getExportAuditEventsUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(filters),
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `auditoria-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      // O download não passa pelo cache de consultas: trata a reautenticação aqui.
      if (isReauthRequired(error)) return redirectToReauth();
      setExportError(errorMessage(error));
    } finally {
      setExporting(false);
    }
  }

  const filterChanged =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value);
      setPage(0);
    };

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium">Auditoria</h1>
          <p className="text-muted-foreground">
            {me.kind === "super_admin"
              ? "Eventos da gestão da instalação e dos Super Administradores."
              : "Eventos de acesso da organização e das pessoas dela."}
          </p>
        </div>
        <Button variant="outline" onClick={exportCsv} disabled={exporting}>
          Exportar CSV
        </Button>
      </div>
      {exportError && <p role="alert">{exportError}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <Input
          placeholder="Pessoa: nome ou e-mail"
          aria-label="Pessoa: nome ou e-mail"
          value={search}
          onChange={(e) => filterChanged(setSearch)(e.target.value)}
          className="max-w-xs"
        />
        <Select value={eventType} onValueChange={filterChanged(setEventType)}>
          <SelectTrigger aria-label="Filtrar por evento" className="w-60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todos os eventos</SelectItem>
            {Object.entries(AUDIT_EVENT_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={result} onValueChange={filterChanged(setResult)}>
          <SelectTrigger aria-label="Filtrar por resultado" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todos os resultados</SelectItem>
            {Object.entries(AUDIT_RESULT_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex flex-col gap-1">
          <Label htmlFor="audit-from">De</Label>
          <Input
            id="audit-from"
            type="date"
            value={from}
            onChange={(e) => filterChanged(setFrom)(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="audit-to">Até</Label>
          <Input
            id="audit-to"
            type="date"
            value={to}
            onChange={(e) => filterChanged(setTo)(e.target.value)}
          />
        </div>
      </div>

      {events.isError && <p role="alert">{errorMessage(events.error)}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Quando</TableHead>
            <TableHead>Quem</TableHead>
            <TableHead>Evento</TableHead>
            <TableHead className="hidden md:table-cell">Alvo</TableHead>
            <TableHead>Resultado</TableHead>
            <TableHead className="hidden lg:table-cell">Origem</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.data?.map((event) => (
            <TableRow key={event.seq}>
              <TableCell className="whitespace-nowrap">
                {formatDateTime(event.occurred_at)}
              </TableCell>
              <TableCell>{actorLabel(event)}</TableCell>
              <TableCell>{AUDIT_EVENT_LABELS[event.event_type] ?? event.event_type}</TableCell>
              <TableCell className="hidden break-all md:table-cell">
                {event.target_name ?? event.target_id ?? "—"}
              </TableCell>
              <TableCell>
                <Badge variant={event.result === "success" ? "secondary" : "outline"}>
                  {AUDIT_RESULT_LABELS[event.result] ?? event.result}
                </Badge>
              </TableCell>
              <TableCell className="hidden lg:table-cell">{event.source_ip ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {events.data?.length === 0 && (
        <p className="text-muted-foreground">Nenhum evento com estes filtros.</p>
      )}

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
        >
          Anteriores
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={(events.data?.length ?? 0) < PAGE}
          onClick={() => setPage((p) => p + 1)}
        >
          Seguintes
        </Button>
      </div>
    </>
  );
}
