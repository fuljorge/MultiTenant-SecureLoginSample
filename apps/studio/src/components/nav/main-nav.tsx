"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";

import { visibleNavItems } from "./nav-items";

/** Menu principal com os itens que o perfil na organização ativa pode usar (RF-014). */
export function MainNav({ permissions }: { permissions: readonly string[] }) {
  const pathname = usePathname();
  const items = visibleNavItems(permissions);

  return (
    <nav
      aria-label="Principal"
      className="order-last flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto sm:flex-1"
    >
      {items.map((item) => {
        const current = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Button key={item.href} variant={current ? "secondary" : "ghost"} size="sm" asChild>
            <Link href={item.href} aria-current={current ? "page" : undefined}>
              {item.label}
            </Link>
          </Button>
        );
      })}
    </nav>
  );
}
