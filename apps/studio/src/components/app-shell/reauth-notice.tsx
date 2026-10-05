"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { consumeReauthFlag } from "@/lib/auth/reauth";

/** Aviso na volta da nova autenticação (RF-031): a ação não é repetida sozinha. */
export function ReauthNotice() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // A marca só existe na URL do navegador; lida depois da montagem, de propósito.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (consumeReauthFlag()) setVisible(true);
  }, []);

  if (!visible) return null;
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted px-4 py-3"
    >
      <span>Identidade confirmada. Repita a ação para concluí-la.</span>
      <Button variant="ghost" size="sm" onClick={() => setVisible(false)}>
        Fechar
      </Button>
    </div>
  );
}
