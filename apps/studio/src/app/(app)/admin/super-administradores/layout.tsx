import type { ReactNode } from "react";

import { RequirePermission } from "@/components/nav/require-permission";

export default function SuperAdminsLayout({ children }: { children: ReactNode }) {
  return <RequirePermission permission="super_admins:manage">{children}</RequirePermission>;
}
