import { describe, expect, it } from "vitest";

import { describeBrowser, formatDateTime } from "./format";

describe("describeBrowser", () => {
  it("resume navegador e sistema", () => {
    const ua =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36";
    expect(describeBrowser(ua)).toBe("Chrome no Windows");
  });

  it("trata ausência de User-Agent", () => {
    expect(describeBrowser(null)).toBe("Navegador desconhecido");
  });
});

describe("formatDateTime", () => {
  it("usa o horário de Brasília", () => {
    expect(formatDateTime("2026-10-02T15:30:00Z")).toBe("02/10/2026, 12:30");
  });
});
