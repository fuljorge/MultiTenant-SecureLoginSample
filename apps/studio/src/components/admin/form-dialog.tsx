"use client";

import { useState, type FormEvent } from "react";

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
import { isReauthRequired, redirectToReauth } from "@/lib/auth/reauth";
import { errorMessage } from "@/lib/labels";

export interface FormField {
  name: string;
  label: string;
  type?: "text" | "email";
  defaultValue?: string;
}

interface Props {
  trigger: string;
  title: string;
  description: string;
  submitLabel: string;
  fields: FormField[];
  /** Envia os valores; resolve com a mensagem de sucesso exibida no diálogo. */
  onSubmit: (values: Record<string, string>) => Promise<string>;
  variant?: "default" | "outline";
}

/** Diálogo com formulário simples (convites e renomeação; US5). */
export function FormDialog({
  trigger,
  title,
  description,
  submitLabel,
  fields,
  onSubmit,
  variant = "default",
}: Props) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const formId = `form-${title.replace(/\W+/g, "-").toLowerCase()}`;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(
      [...new FormData(event.currentTarget).entries()].map(([k, v]) => [k, String(v)]),
    );
    setPending(true);
    setError(null);
    try {
      setDone(await onSubmit(values));
    } catch (exc) {
      // Chamadas diretas não passam pelo cache de mutações: reautenticação aqui (RF-031).
      if (isReauthRequired(exc)) return redirectToReauth();
      setError(errorMessage(exc));
    } finally {
      setPending(false);
    }
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setDone(null);
      setError(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant={variant}>{trigger}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {done ? (
          <p role="status">{done}</p>
        ) : (
          <form id={formId} onSubmit={submit} className="flex flex-col gap-4">
            {fields.map((field) => (
              <div key={field.name} className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-${field.name}`}>{field.label}</Label>
                <Input
                  id={`${formId}-${field.name}`}
                  name={field.name}
                  type={field.type ?? "text"}
                  defaultValue={field.defaultValue}
                  required
                  maxLength={200}
                />
              </div>
            ))}
            {error && <p role="alert">{error}</p>}
          </form>
        )}

        <DialogFooter>
          {done ? (
            <Button onClick={() => onOpenChange(false)}>Fechar</Button>
          ) : (
            <Button type="submit" form={formId} disabled={pending}>
              {submitLabel}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
