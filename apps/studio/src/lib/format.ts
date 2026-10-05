const dateTime = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: "America/Sao_Paulo",
});

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

/** Resumo legível do navegador a partir do User-Agent. */
export function describeBrowser(userAgent: string | null | undefined): string {
  if (!userAgent) return "Navegador desconhecido";
  const browser =
    [
      ["Edg/", "Edge"],
      ["Chrome/", "Chrome"],
      ["Firefox/", "Firefox"],
      ["Safari/", "Safari"],
    ].find(([token]) => userAgent.includes(token))?.[1] ?? "Navegador";
  const system =
    [
      ["Windows", "Windows"],
      ["Android", "Android"],
      ["iPhone", "iOS"],
      ["Mac OS", "macOS"],
      ["Linux", "Linux"],
    ].find(([token]) => userAgent.includes(token))?.[1] ?? "";
  return system ? `${browser} no ${system}` : browser;
}
