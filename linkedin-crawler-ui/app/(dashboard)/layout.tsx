import { DashboardShell } from "@/components/features/dashboard/DashboardShell";

export default function DashboardRouteLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <DashboardShell>{children}</DashboardShell>;
}
