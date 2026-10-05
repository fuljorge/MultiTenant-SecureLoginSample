import type { ReactNode } from "react";

import { AUDIT_PERMISSIONS } from "@/components/nav/nav-items";
import { RequirePermission } from "@/components/nav/require-permission";

export default function AuditLayout({ children }: { children: ReactNode }) {
  return <RequirePermission permission={AUDIT_PERMISSIONS}>{children}</RequirePermission>;
}
