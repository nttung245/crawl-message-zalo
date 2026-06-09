import { Metadata } from "next";
import { AutoSendCampaignContent } from "@/components/features/campaigns/AutoSendCampaignContent";

export const metadata: Metadata = {
  title: "Tạo chiến dịch mới",
  description: "Cấu hình chiến dịch auto send",
};

export default function CampaignPage() {
  return (
    <div className="flex h-full w-full flex-col">
      <AutoSendCampaignContent />
    </div>
  );
}
