"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "@cap/api-client";

import { isReauthRequired, redirectToReauth } from "@/lib/auth/reauth";

// Ação sensível com login antigo (RF-031): leva à nova autenticação e volta à mesma tela.
function onApiError(error: unknown) {
  if (isReauthRequired(error)) redirectToReauth();
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({ onError: onApiError }),
        mutationCache: new MutationCache({ onError: onApiError }),
        defaultOptions: {
          queries: {
            // 401 e 403 não melhoram com nova tentativa.
            retry: (count, error) =>
              !(error instanceof ApiError && [401, 403].includes(error.status)) && count < 2,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
