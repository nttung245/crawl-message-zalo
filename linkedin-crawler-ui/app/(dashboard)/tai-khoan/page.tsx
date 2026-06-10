import { Metadata } from "next";
import { AccountsDashboardContent } from "@/components/features/accounts/AccountsDashboardContent";

export const metadata: Metadata = {
  title: "Quản lý tài khoản",
  description: "Quản lý đa tài khoản kết nối",
};

export default function AccountsPage() {
  return (
    <div className="flex h-full w-full flex-col">
      <AccountsDashboardContent />
    </div>
  );
}
