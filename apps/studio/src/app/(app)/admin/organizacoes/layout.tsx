import type { ReactNode } from "react";

import { RequirePermission } from "@/components/nav/require-permission";

export default function OrganizationsLayout({ children }: { children: ReactNode }) {
  return <RequirePermission permission="organizations:manage">{children}</RequirePermission>;
}
