import Link from "next/link";

import { N8nManagedGroupsSection } from "./N8nManagedGroupsSection";

export function GroupManagementPageContent() {
  return (
    <>
      <div className="mb-xl">
        <h1 className="text-h1 text-on-surface mb-xs font-semibold">Quản lý nhóm</h1>
        
      </div>

      <N8nManagedGroupsSection />
    </>
  );
}
