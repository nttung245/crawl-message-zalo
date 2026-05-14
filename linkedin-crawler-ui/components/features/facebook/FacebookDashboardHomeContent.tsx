"use client";

import { MaterialIcon } from "@/components/ui";
import {DashboardPosts} from "../../nguyen/modules/crawldFB/components/dashboardPost"
import CrawlFb_form from "@/components/nguyen/modules/crawldFB/components/crawlFB_form";
/**
 * Khung feed / bảng / card / chi tiết cho Facebook — team Facebook tự triển khai tại đây
 * (hoặc tách thêm module con). Sidebar và chọn nền tảng dùng chung với LinkedIn.
 */
export function FacebookDashboardHomeContent() {
  return (
    <DashboardPosts/>
   
  );
}
