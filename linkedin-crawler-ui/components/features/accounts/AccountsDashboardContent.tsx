"use client";

import React, { useState, useEffect } from "react";
import { MaterialIcon } from "@/components/ui";
import { getAllLinkedInAccounts, removeLinkedInAccount, setActiveAccount, type CredentialRecord } from "@/lib/credentials";

export function AccountsDashboardContent() {
  const [accounts, setAccounts] = useState<CredentialRecord[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setAccounts(getAllLinkedInAccounts());
  }, []);

  const handleDisconnect = (email: string) => {
    removeLinkedInAccount(email);
    setAccounts(getAllLinkedInAccounts());
  };

  const handleChat = (id: string) => {
    setActiveAccount(id);
    // You can redirect to a specific chat view if needed
    alert("Đã chuyển sang tài khoản " + id);
  };

  const filtered = search
    ? accounts.filter((a) => a.email.includes(search) || a.name?.includes(search) || a.phone?.includes(search))
    : accounts;

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-[#f8f6f2] min-h-screen">
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <h2 className="text-xl font-bold text-slate-800">Dashboard</h2>
        <span className="text-xs text-slate-600 bg-slate-200/60 px-3 py-1 rounded-full font-medium border border-slate-300/40">
          {accounts.length} tài khoản
        </span>

        <div className="ml-auto flex items-center gap-3 flex-wrap">
          <button className="flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 shadow-sm transition-all">
            <MaterialIcon name="group" className="text-sm" />
            Gộp tài khoản
          </button>
          <button className="flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-xl bg-sky-100 hover:bg-sky-200 text-sky-700 border border-sky-200 shadow-sm transition-all">
            <MaterialIcon name="support_agent" className="text-sm" />
            Hỗ trợ
          </button>
          <div className="relative">
            <MaterialIcon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tên, SĐT, UID..."
              className="bg-white text-slate-700 placeholder-slate-400 text-sm pl-9 pr-4 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 w-56 shadow-sm transition-all"
            />
          </div>
        </div>
      </div>

      <p className="text-xs text-slate-500 mb-4 flex items-center gap-1 font-medium">
        <MaterialIcon name="drag_indicator" className="text-sm" />
        Kéo thả để sắp xếp thứ tự
      </p>

      <div className="flex items-center gap-3 mt-6 mb-5">
        <h3 className="text-sm font-bold text-slate-700">Tài khoản</h3>
        <span className="text-xs text-slate-500 bg-slate-200/60 px-2 py-0.5 rounded-full font-medium border border-slate-300/40">{accounts.length}</span>
        <div className="flex-1 border-t border-slate-200" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        {filtered.map((acc) => (
          <div key={acc.id} className="bg-[#f2ede6] rounded-2xl p-4 shadow-sm border border-[#e8e2da] hover:shadow-md transition-shadow relative group">
            <div className="flex items-start gap-4 mb-4">
              <div className="relative">
                <div className="w-12 h-12 bg-slate-200 rounded-full flex items-center justify-center text-xl font-bold text-slate-500 overflow-hidden border-2 border-white shadow-sm">
                  {acc.avatar ? <img src={acc.avatar} alt="avatar" className="w-full h-full object-cover" /> : (acc.name?.charAt(0).toUpperCase() || acc.email.charAt(0).toUpperCase())}
                </div>
                <div className={`absolute bottom-0 right-0 w-3.5 h-3.5 border-2 border-white rounded-full ${acc.status === 'connected' ? 'bg-green-500' : 'bg-slate-400'}`} />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-bold text-slate-800 truncate text-base">{acc.name || acc.email.split('@')[0]}</h4>
                <p className="text-xs text-slate-600 truncate mt-0.5 font-medium">{acc.email}</p>
                {acc.phone && (
                  <p className="text-xs text-slate-500 mt-1 flex items-center gap-1 font-medium">
                    <MaterialIcon name="call" className="text-[12px] text-pink-500" />
                    {acc.phone}
                  </p>
                )}
              </div>
              <button className="text-slate-400 hover:text-slate-600 p-1">
                <MaterialIcon name="more_vert" className="text-lg" />
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => handleChat(acc.id)}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 rounded-xl text-sm transition-colors shadow-sm shadow-blue-600/20"
              >
                Chat
              </button>
              <button 
                onClick={() => handleDisconnect(acc.email)}
                className="flex-1 bg-[#e4dfd8] hover:bg-[#d8d3cc] text-slate-700 font-semibold py-2 rounded-xl text-sm transition-colors border border-[#d5d0c9]"
              >
                Ngắt kết nối
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
