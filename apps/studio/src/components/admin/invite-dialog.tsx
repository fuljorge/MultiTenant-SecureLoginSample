"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  getListInvitationsQueryKey,
  getListUsersQueryKey,
  useCreateInvitation,
  type Profile,
} from "@cap/api-client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { errorMessage, PROFILE_LABELS, PROFILES } from "@/lib/labels";

/** Convite de pessoa para a organização ativa (US3 cenário 1). */
export function InviteDialog({ organizationId }: { organizationId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState<Profile>("agent_designer");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const invite = useCreateInvitation({
    mutation: {
      onSuccess: (_, variables) => {
        setSentTo(variables.data.email);
        queryClient.invalidateQueries({ queryKey: getListInvitationsQueryKey() });
        queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() });
      },
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    invite.mutate({
      data: {
        name: String(form.get("name")),
        email: String(form.get("email")),
        organization_id: organizationId,
        profile,
      },
    });
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setSentTo(null);
      invite.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button>Convidar pessoa</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Convidar pessoa</DialogTitle>
          <DialogDescription>
            A pessoa recebe um e-mail com um link de uso único para entrar.
          </DialogDescription>
        </DialogHeader>

        {sentTo ? (
          <p role="status">Convite enviado para {sentTo}.</p>
        ) : (
          <form id="invite-form" onSubmit={submit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="invite-name">Nome</Label>
              <Input id="invite-name" name="name" required maxLength={200} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="invite-email">E-mail</Label>
              <Input id="invite-email" name="email" type="email" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="invite-profile">Perfil</Label>
              <Select value={profile} onValueChange={(v) => setProfile(v as Profile)}>
                <SelectTrigger id="invite-profile" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROFILES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {PROFILE_LABELS[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {invite.isError && <p role="alert">{errorMessage(invite.error)}</p>}
          </form>
        )}

        <DialogFooter>
          {sentTo ? (
            <Button onClick={() => onOpenChange(false)}>Fechar</Button>
          ) : (
            <Button type="submit" form="invite-form" disabled={invite.isPending}>
              Enviar convite
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
