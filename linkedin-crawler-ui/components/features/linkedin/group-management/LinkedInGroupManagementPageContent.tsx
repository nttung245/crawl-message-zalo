import { LinkedInN8nManagedGroupsSection } from "./LinkedInN8nManagedGroupsSection";

export function LinkedInGroupManagementPageContent() {
  return (
    <>
      <div className="mb-xl">
        <h1 className="text-h1 text-on-surface mb-xs font-semibold">Quản lý nhóm</h1>
      </div>

      <LinkedInN8nManagedGroupsSection />
    </>
  );
}
