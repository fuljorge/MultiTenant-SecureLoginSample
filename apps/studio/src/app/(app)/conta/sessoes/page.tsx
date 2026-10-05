"use client";

import { useQueryClient } from "@tanstack/react-query";

import { getMySessionsQueryKey, useEndMySession, useMySessions } from "@cap/api-client";

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
import { describeBrowser, formatDateTime } from "@/lib/format";

/** Minhas sessões (US1; RF-006): ver onde estou logado e encerrar sessões. */
export default function MySessionsPage() {
  const queryClient = useQueryClient();
  const sessions = useMySessions();
  const endSession = useEndMySession({
    mutation: {
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getMySessionsQueryKey() }),
    },
  });

  return (
    <>
      <div>
        <h1 className="text-2xl font-medium">Minhas sessões</h1>
        <p className="text-muted-foreground">
          Lugares onde você está logado. Encerre as que não reconhecer.
        </p>
      </div>

      {sessions.isPending && <p className="text-muted-foreground">Carregando…</p>}
      {sessions.isError && <p role="alert">Não foi possível carregar as sessões.</p>}

      {sessions.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Navegador</TableHead>
              <TableHead className="hidden sm:table-cell">Rede</TableHead>
              <TableHead>Último uso</TableHead>
              <TableHead className="sr-only">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.data.map((session) => (
              <TableRow key={session.id}>
                <TableCell>
                  {describeBrowser(session.user_agent)}
                  {session.current && (
                    <Badge variant="secondary" className="ml-2">
                      Esta sessão
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  {session.source_ip_partial ?? "—"}
                </TableCell>
                <TableCell>{formatDateTime(session.last_seen_at)}</TableCell>
                <TableCell className="text-right">
                  {!session.current && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={endSession.isPending}
                      onClick={() => endSession.mutate({ sessionId: session.id })}
                    >
                      Encerrar
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
