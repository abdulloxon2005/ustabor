export const colors = {
  primary: "#2563EB",
  primaryDark: "#1D4ED8",
  primarySoft: "#DBEAFE",
  bg: "#F3F4F6",
  card: "#FFFFFF",
  text: "#111827",
  muted: "#6B7280",
  border: "#E5E7EB",
  danger: "#DC2626",
  dangerSoft: "#FEE2E2",
  success: "#16A34A",
  successSoft: "#DCFCE7",
  warning: "#D97706",
  warningSoft: "#FEF3C7",
  star: "#F59E0B",
};

export const radius = { sm: 8, md: 12, lg: 16 };

export const statusStyle: Record<string, { label: string; color: string; bg: string }> = {
  searching: { label: "Qidirilmoqda", color: colors.warning, bg: colors.warningSoft },
  assigned: { label: "Biriktirildi", color: colors.primary, bg: colors.primarySoft },
  in_progress: { label: "Jarayonda", color: "#7C3AED", bg: "#EDE9FE" },
  completed: { label: "Yakunlandi", color: colors.success, bg: colors.successSoft },
  cancelled: { label: "Bekor qilindi", color: colors.danger, bg: colors.dangerSoft },
};

export function formatPrice(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n.toLocaleString("ru-RU")} so'm`;
}

export function formatDate(iso: string): string {
  // Backend UTC vaqtni "Z"siz berishi mumkin
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
