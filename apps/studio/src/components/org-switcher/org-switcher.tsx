"use client";

import { useSwitchOrganization, type MeOut } from "@cap/api-client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PROFILE_LABELS } from "@/lib/labels";

/** Troca a organização ativa sem novo login (US5; RF-019). Só aparece com mais de uma. */
export function OrgSwitcher({ me }: { me: MeOut }) {
  const switchOrganization = useSwitchOrganization({
    mutation: {
      // Recarga completa de propósito: menus, permissões e dados passam a ser os da nova
      // organização, sem sobra em cache da anterior.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      onSuccess: () => window.location.assign("/"),
    },
  });

  if (me.organizations.length < 2 || !me.active_organization_id) return null;

  return (
    <Select
      value={me.active_organization_id}
      onValueChange={(organizationId) =>
        switchOrganization.mutate({ data: { organization_id: organizationId } })
      }
      disabled={switchOrganization.isPending}
    >
      <SelectTrigger aria-label="Organização ativa" className="w-48 sm:w-56">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {me.organizations.map((organization) => (
          <SelectItem key={organization.id} value={organization.id}>
            {organization.name}
            <span className="text-muted-foreground">
              {" "}
              · {PROFILE_LABELS[organization.profile as keyof typeof PROFILE_LABELS]}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
