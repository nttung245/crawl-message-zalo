"use client";

import { useState } from "react";
import { MaterialIcon } from "@/components/ui";

interface WelcomeRoleModalProps {
  isOpen: boolean;
  onSelect: (role: "leader" | "member") => void;
  confirmLeaderRoleWithSheet: (code: string) => Promise<void>;
}

export function WelcomeRoleModal({
  isOpen,
  onSelect,
  confirmLeaderRoleWithSheet,
}: WelcomeRoleModalProps) {
  const [selectedRole, setSelectedRole] = useState<"leader" | "member">("member");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    if (selectedRole === "leader") {
      if (!code.trim()) {
        setError("Vui lòng nhập mã code Leader.");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await confirmLeaderRoleWithSheet(code.trim());
        onSelect("leader");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Lỗi xác thực hoặc đồng bộ sheet.",
        );
      } finally {
        setBusy(false);
      }
    } else {
      localStorage.setItem("linkedin_crawler_role", "member");
      onSelect("member");
    }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-md bg-surface/80 backdrop-blur-md">
      <div className="w-[min(92vw,450px)] bg-surface rounded-2xl border border-outline-variant p-xl shadow-2xl space-y-lg animate-in fade-in zoom-in duration-300">
        <div className="text-center space-y-xs">
          <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary mb-md">
            <MaterialIcon name="verified_user" className="text-4xl" />
          </div>
          <h2 className="text-h2 font-black text-on-surface">CHÀO MỪNG BẠN</h2>
          <p className="text-body-md text-on-surface-variant">Vui lòng chọn vai trò của bạn để tiếp tục</p>
        </div>

        <div className="grid grid-cols-2 gap-md">
          <label 
            className={`
              flex flex-col items-center gap-sm p-lg rounded-xl border-2 cursor-pointer transition-all
              ${selectedRole === "member" ? "border-primary bg-primary/5" : "border-outline-variant hover:border-outline"}
            `}
          >
            <input 
              type="radio" 
              name="role" 
              className="hidden" 
              checked={selectedRole === "member"} 
              onChange={() => { setSelectedRole("member"); setError(null); }}
            />
            <MaterialIcon name="person" className={selectedRole === "member" ? "text-primary" : "text-on-surface-variant"} />
            <span className={`font-bold ${selectedRole === "member" ? "text-primary" : "text-on-surface-variant"}`}>Thành Viên</span>
          </label>

          <label 
            className={`
              flex flex-col items-center gap-sm p-lg rounded-xl border-2 cursor-pointer transition-all
              ${selectedRole === "leader" ? "border-primary bg-primary/5" : "border-outline-variant hover:border-outline"}
            `}
          >
            <input 
              type="radio" 
              name="role" 
              className="hidden" 
              checked={selectedRole === "leader"} 
              onChange={() => { setSelectedRole("leader"); setError(null); }}
            />
            <MaterialIcon name="shield_person" className={selectedRole === "leader" ? "text-primary" : "text-on-surface-variant"} />
            <span className={`font-bold ${selectedRole === "leader" ? "text-primary" : "text-on-surface-variant"}`}>Leader</span>
          </label>
        </div>

        {selectedRole === "leader" && (
          <div className="space-y-base animate-in slide-in-from-top-2">
            <label className="text-label-md font-bold text-on-surface-variant">Nhập mã code xác nhận</label>
            <input 
              type="password"
              placeholder="••••"
              className="w-full bg-surface-container-low border border-outline-variant rounded-lg px-md py-sm text-center text-xl tracking-[1em] outline-none focus:ring-2 focus:ring-primary"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={busy}
            />
          </div>
        )}

        {error && (
          <div className="flex items-center gap-xs text-error bg-error-container/20 p-sm rounded border border-error-container text-body-sm">
            <MaterialIcon name="error" className="text-lg" />
            {error}
          </div>
        )}

        <button 
          onClick={handleConfirm}
          disabled={busy}
          className="w-full bg-primary text-on-primary py-md rounded-xl font-h3 font-bold uppercase hover:brightness-110 disabled:opacity-50 transition-all shadow-lg shadow-primary/20"
        >
          {busy ? "Đang xác thực..." : "Vào Dashboard"}
        </button>
      </div>
    </div>
  );
}
