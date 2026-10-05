import type { ReactNode } from "react";

import { RequirePermission } from "@/components/nav/require-permission";

export default function UsersLayout({ children }: { children: ReactNode }) {
  return <RequirePermission permission="users:read">{children}</RequirePermission>;
}
