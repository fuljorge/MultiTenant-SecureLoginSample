import type { ReactNode } from "react";

import { RequirePermission } from "@/components/nav/require-permission";

export default function SecurityLayout({ children }: { children: ReactNode }) {
  return <RequirePermission permission="security:manage">{children}</RequirePermission>;
}
