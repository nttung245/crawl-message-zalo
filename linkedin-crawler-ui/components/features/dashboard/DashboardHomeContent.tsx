import { CrawlerConfigCard } from "./CrawlerConfigCard";
import { CrawlResultsSection } from "./CrawlResultsSection";

export function DashboardHomeContent() {
  return (
    <>
      <div className="mb-xl">
        <h1 className="text-h1 text-on-surface mb-xs font-semibold">
          LinkedIn Group Crawler
        </h1>
        <p className="text-body-lg text-on-surface-variant">
          Thu thập và phân tích dữ liệu từ nhiều nhóm LinkedIn một cách hiệu quả.
        </p>
      </div>

      <div className="mb-xl max-w-2xl">
        <CrawlerConfigCard />
      </div>

      <div className="mb-xl">
        <CrawlResultsSection />
      </div>
    </>
  );
}
