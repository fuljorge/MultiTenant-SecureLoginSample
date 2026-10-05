export interface NavItem {
  href: string;
  label: string;
  /** Valores de `MeOut.permissions` (ex.: `users:read`); qualquer um basta. */
  permissions: string[];
}

// Links exibidos conforme as permissões do perfil na organização ativa (RF-014). Só
// orientam a interface: quem decide é a API.
/** Auditoria da organização (Administrador) ou da instalação (Super Administrador). */
export const AUDIT_PERMISSIONS = ["audit:read", "audit:read:installation"];

// O Super Administrador só tem as áreas da instalação; os perfis, as da organização.
export const NAV_ITEMS: NavItem[] = [
  { href: "/admin/organizacoes", label: "Organizações", permissions: ["organizations:manage"] },
  {
    href: "/admin/super-administradores",
    label: "Super Administradores",
    permissions: ["super_admins:manage"],
  },
  { href: "/admin/usuarios", label: "Usuários", permissions: ["users:read"] },
  { href: "/admin/seguranca", label: "Segurança", permissions: ["security:manage"] },
  { href: "/admin/auditoria", label: "Auditoria", permissions: AUDIT_PERMISSIONS },
];

export function visibleNavItems(permissions: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => item.permissions.some((p) => permissions.includes(p)));
}
