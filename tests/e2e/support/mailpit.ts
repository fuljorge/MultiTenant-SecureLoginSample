/**
 * Leitura de e-mails capturados pelo Mailpit (ambiente local e CI).
 * Usado pelos testes para obter o código do segundo fator e links de convite.
 */
const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://localhost:8025";

interface MailpitMessageSummary {
  ID: string;
  To: { Address: string }[];
  Subject: string;
  Created: string;
}

export interface MailpitMessage {
  ID: string;
  Subject: string;
  Text: string;
  HTML: string;
  /** Quando o Mailpit recebeu o e-mail (ISO 8601). */
  Created: string;
}

async function searchMessages(query: string): Promise<MailpitMessageSummary[]> {
  const url = `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(query)}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Mailpit respondeu ${response.status}`);
  const body = (await response.json()) as { messages: MailpitMessageSummary[] };
  return body.messages;
}

async function getMessage(id: string): Promise<MailpitMessage> {
  const response = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`);
  if (!response.ok) throw new Error(`Mailpit respondeu ${response.status}`);
  return (await response.json()) as MailpitMessage;
}

/** Espera o e-mail mais recente para `to` recebido depois de `since`. */
export async function waitForEmail(
  to: string,
  since: Date,
  timeoutMs = 60_000,
): Promise<MailpitMessage> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const messages = await searchMessages(`to:${to}`);
    const latest = messages
      .filter((m) => new Date(m.Created) >= since)
      .sort((a, b) => b.Created.localeCompare(a.Created))[0];
    if (latest) return { ...(await getMessage(latest.ID)), Created: latest.Created };
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Nenhum e-mail para ${to} em ${timeoutMs} ms`);
}

/** Extrai o código numérico de 6 dígitos do corpo do e-mail. */
export function extractCode(message: MailpitMessage): string {
  const match = /\b(\d{6})\b/.exec(message.Text);
  if (!match) throw new Error("Código não encontrado no e-mail");
  return match[1];
}

/** Extrai o primeiro link https do corpo do e-mail. */
export function extractLink(message: MailpitMessage): string {
  const match = /https?:\/\/\S+/.exec(message.Text);
  if (!match) throw new Error("Link não encontrado no e-mail");
  return match[0];
}
