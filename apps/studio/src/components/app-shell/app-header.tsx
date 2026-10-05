"use client";

import Image from "next/image";
import Link from "next/link";
import { ChevronDown, KeyRound, LogOut, MonitorSmartphone } from "lucide-react";

import { useLogout, type MeOut } from "@cap/api-client";

import { MainNav } from "@/components/nav/main-nav";
import { OrgSwitcher } from "@/components/org-switcher/org-switcher";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { scopeLabel } from "@/lib/auth/session";

export function AppHeader({ me }: { me: MeOut }) {
  const logout = useLogout({
    mutation: {
      // Recarga completa de propósito: sem sessão, a página inicial recomeça o login, que
      // passa pelo Keycloak (fora do roteador do Next.js).
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      onSettled: () => window.location.assign("/"),
    },
  });
  const organization = scopeLabel(me);

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border bg-sidebar px-4 py-3 sm:flex-nowrap sm:px-6">
      <Link href="/" className="flex items-center gap-3">
        <Image
          src="/brand/logo-claro.png"
          alt="SecureLogin"
          width={36}
          height={36}
          className="size-9"
          priority
        />
        <span className="font-medium">SecureLogin</span>
      </Link>

      <MainNav permissions={me.permissions} />

      <OrgSwitcher me={me} />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="gap-2" aria-label="Menu da conta">
            <span className="flex flex-col items-end leading-tight">
              <span className="text-sm">{me.name}</span>
              {organization && (
                <span className="text-xs text-muted-foreground">{organization}</span>
              )}
            </span>
            <ChevronDown className="size-4" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="truncate font-normal text-muted-foreground">
            {me.email}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link href="/conta/sessoes">
              <MonitorSmartphone aria-hidden /> Minhas sessões
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            {/* Navegação completa: a troca de senha acontece nas telas do Keycloak. */}
            <a href="/api/v1/auth/password">
              <KeyRound aria-hidden /> Trocar senha
            </a>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => logout.mutate()} disabled={logout.isPending}>
            <LogOut aria-hidden /> Sair
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
