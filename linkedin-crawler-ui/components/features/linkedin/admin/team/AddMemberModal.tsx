"use client";

import { useState } from "react";
import { addMember } from "@/services/linkedinCrawlerService";

interface AddMemberModalProps {
  isOpen: boolean;
  onClose: () => void;
  leaderEmail: string;
  onSuccess?: () => void;
}

export function AddMemberModal({
  isOpen,
  onClose,
  leaderEmail,
  onSuccess,
}: AddMemberModalProps) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    
    setBusy(true);
    setError(null);
    try {
      const res = await addMember({
        email_member: email.trim(),
        email_leader: leaderEmail,
      });
      if (res.success) {
        onSuccess?.();
        setEmail("");
        onClose();
      } else {
        setError(res.message || "Thêm thành viên thất bại.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi hệ thống.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-md">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-[min(92vw,400px)] bg-surface rounded-xl border border-outline-variant p-lg shadow-2xl">
        <h3 className="text-h3 font-bold text-on-surface mb-md">Thêm Thành Viên</h3>
        
        <form onSubmit={handleSubmit} className="space-y-md">
          <div className="flex flex-col gap-base">
            <label className="text-label-md font-semibold text-on-surface-variant">Email Member</label>
            <input
              type="email"
              placeholder="nhap-email@gmail.com"
              className="bg-surface-container-low border border-outline-variant rounded-lg px-md py-sm focus:ring-2 focus:ring-primary outline-none"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>

          {error && (
            <p className="text-error text-body-sm bg-error-container/20 p-sm rounded border border-error-container">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-sm mt-lg">
            <button
              type="button"
              className="px-lg py-sm rounded-lg text-body-md font-bold uppercase hover:bg-surface-container-high transition-colors"
              onClick={onClose}
              disabled={busy}
            >
              Hủy
            </button>
            <button
              type="submit"
              className="bg-primary text-on-primary px-xl py-sm rounded-lg text-body-md font-bold uppercase hover:brightness-110 disabled:opacity-50 transition-all"
              disabled={busy}
            >
              {busy ? "Đang xử lý..." : "Thêm Ngay"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
