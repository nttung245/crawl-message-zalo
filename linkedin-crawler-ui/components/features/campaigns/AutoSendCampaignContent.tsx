"use client";

import React, { useState } from "react";
import { MaterialIcon } from "@/components/ui";

export function AutoSendCampaignContent() {
  const [campaignName, setCampaignName] = useState("Giới thiệu sản phẩm");
  const [campaignType, setCampaignType] = useState("Hỗn hợp");
  const [actions, setActions] = useState({ message: true, addFriend: true, inviteGroup: false });
  const [delay, setDelay] = useState("2 phút");
  
  const [content1, setContent1] = useState("Em chào anh {name},\nMột mức giá không tưởng với Masteri Cao Xà Lá\n🔥 Giữa lúc các hàng xóm xung quanh đang đồn thổi về mức giá mở bán của Mas CXL toàn trên zời thì CĐT tung ra mức dự kiến khiến ai cũng đứng hình\n🍀 Giữa trung tâm Hà Nội - Không vội không còn hàng đâu các bác ơi!");
  const [content2, setContent2] = useState("");
  
  const [addFriendMsg, setAddFriendMsg] = useState("Em chào anh {name}, Mas CXL ra hàng rồi ạ, anh quan tâm sản phẩm ib em nha!");

  return (
    <div className="flex-1 overflow-hidden p-6 bg-[#f8f6f2] min-h-screen flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-6xl overflow-hidden flex flex-col border border-slate-200 max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-pink-100 rounded-xl flex items-center justify-center text-xl shadow-sm">🚀</div>
            <div>
              <h2 className="text-lg font-bold text-slate-800">Tạo chiến dịch mới</h2>
              <p className="text-xs text-slate-500 font-medium">Cấu hình nội dung và phương thức gửi</p>
            </div>
          </div>
          <button className="text-slate-400 hover:text-slate-600 p-2 rounded-full hover:bg-slate-100 transition-colors">
            <MaterialIcon name="close" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar */}
          <div className="w-64 border-r border-slate-100 p-5 overflow-y-auto bg-slate-50/30">
            <div className="mb-6">
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2 block">Tên chiến dịch *</label>
              <input 
                type="text" 
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 shadow-sm"
              />
            </div>

            <div className="mb-6">
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2 block">Loại *</label>
              <div className="space-y-1.5">
                {['Tin nhắn', 'Kết bạn', 'Mời nhóm', 'Hỗn hợp'].map((type) => (
                  <button 
                    key={type}
                    onClick={() => setCampaignType(type)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                      campaignType === type 
                        ? 'bg-blue-50 text-blue-700 border border-blue-200 shadow-sm' 
                        : 'text-slate-600 hover:bg-slate-100 border border-transparent'
                    }`}
                  >
                    <MaterialIcon name={type === 'Tin nhắn' ? 'chat' : type === 'Kết bạn' ? 'person_add' : type === 'Mời nhóm' ? 'groups' : 'shuffle'} className={`text-lg ${campaignType === type ? 'text-blue-500' : 'text-slate-400'}`} />
                    {type}
                    {campaignType === type && <MaterialIcon name="check_circle" className="ml-auto text-sm text-blue-500" />}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-6">
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2 block">Hành động</label>
              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input type="checkbox" checked={actions.message} onChange={(e) => setActions({...actions, message: e.target.checked})} className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300" />
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700 group-hover:text-slate-900"><MaterialIcon name="chat" className="text-purple-400 text-lg" /> Tin nhắn</div>
                </label>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input type="checkbox" checked={actions.addFriend} onChange={(e) => setActions({...actions, addFriend: e.target.checked})} className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300" />
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700 group-hover:text-slate-900"><MaterialIcon name="waving_hand" className="text-amber-400 text-lg" /> Kết bạn</div>
                </label>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input type="checkbox" checked={actions.inviteGroup} onChange={(e) => setActions({...actions, inviteGroup: e.target.checked})} className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300" />
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700 group-hover:text-slate-900"><MaterialIcon name="groups" className="text-indigo-400 text-lg" /> Mời nhóm</div>
                </label>
              </div>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2 block flex items-center gap-1"><MaterialIcon name="timer" className="text-[14px]" /> Delay</label>
              <div className="grid grid-cols-2 gap-2">
                {['5s', '15s', '30s', '1 phút', '2 phút', '3 phút'].map((d) => (
                  <button 
                    key={d}
                    onClick={() => setDelay(d)}
                    className={`py-2 text-xs font-semibold rounded-xl border transition-all ${
                      delay === d 
                        ? 'bg-blue-50 border-blue-200 text-blue-700 shadow-sm' 
                        : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 flex flex-col min-w-0 bg-white">
            <div className="flex-1 overflow-y-auto p-6">
              {/* Tabs */}
              <div className="flex items-center gap-2 mb-4 border-b border-slate-100 pb-4">
                <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-semibold shadow-sm shadow-blue-600/20">
                  <span className="w-5 h-5 bg-white/20 rounded-md flex items-center justify-center text-[11px]">1</span>
                  Nội dung 1
                  <MaterialIcon name="close" className="text-[14px] ml-1 opacity-60 hover:opacity-100" />
                </button>
                <button className="flex items-center gap-2 px-4 py-2 bg-white text-slate-600 border border-slate-200 rounded-xl text-sm font-semibold hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-slate-100 text-slate-500 rounded-md flex items-center justify-center text-[11px]">2</span>
                  Nội dung 2
                  <MaterialIcon name="close" className="text-[14px] ml-1 opacity-60 hover:opacity-100" />
                </button>
                <button className="w-9 h-9 flex items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-700 transition-colors border-dashed">
                  <MaterialIcon name="add" />
                </button>
                
                <div className="ml-auto flex items-center gap-2">
                  <button className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg text-xs font-bold border border-blue-100">
                    <MaterialIcon name="shuffle" className="text-[14px]" /> Random
                  </button>
                  <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-slate-600 border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-50">
                    <MaterialIcon name="list" className="text-[14px]" /> Tất cả
                  </button>
                </div>
              </div>

              {/* Message Editor */}
              <div className="bg-[#f8f9fa] rounded-2xl border border-slate-200 p-1 mb-6">
                <div className="bg-white rounded-xl p-4 min-h-[200px]">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-xs font-medium text-slate-500">Chèn biến:</span>
                    <button className="px-2.5 py-1 bg-blue-50 text-blue-600 text-xs font-bold rounded-lg hover:bg-blue-100 transition-colors">{`{name}`}</button>
                    <button className="px-2.5 py-1 bg-blue-50 text-blue-600 text-xs font-bold rounded-lg hover:bg-blue-100 transition-colors">{`{userId}`}</button>
                  </div>
                  <textarea 
                    value={content1}
                    onChange={(e) => setContent1(e.target.value)}
                    className="w-full h-40 resize-none outline-none text-sm text-slate-700 leading-relaxed"
                    placeholder="Nhập nội dung tin nhắn..."
                  />
                </div>
                <div className="p-3 border-t border-slate-100 flex items-center gap-2">
                  <div className="w-12 h-12 bg-slate-200 rounded-lg overflow-hidden border border-slate-300">
                    <img src="https://picsum.photos/100" alt="img1" className="w-full h-full object-cover" />
                  </div>
                  <div className="w-12 h-12 bg-slate-200 rounded-lg overflow-hidden border border-slate-300">
                    <img src="https://picsum.photos/100?random=1" alt="img2" className="w-full h-full object-cover" />
                  </div>
                </div>
                <button className="w-full py-2.5 text-xs font-bold text-slate-500 bg-slate-50 hover:bg-slate-100 transition-colors rounded-b-xl border-t border-slate-200 flex items-center justify-center gap-2 border-dashed">
                  <MaterialIcon name="image" className="text-[16px]" /> 2 ảnh - thêm tiếp
                </button>
              </div>

              {/* Add friend message */}
              <div className="mb-2">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
                    <MaterialIcon name="waving_hand" className="text-amber-400 text-lg" />
                    Lời nhắn kết bạn
                  </h3>
                  <div className="flex gap-2">
                    <button className="px-2.5 py-1 bg-blue-50 text-blue-600 text-[10px] font-bold rounded-lg">{`{name}`}</button>
                    <button className="px-2.5 py-1 bg-blue-50 text-blue-600 text-[10px] font-bold rounded-lg">{`{userId}`}</button>
                  </div>
                </div>
                <textarea 
                  value={addFriendMsg}
                  onChange={(e) => setAddFriendMsg(e.target.value)}
                  className="w-full border border-slate-200 rounded-2xl p-4 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 shadow-sm resize-none"
                  rows={3}
                />
              </div>
            </div>
            
            {/* Footer */}
            <div className="p-4 border-t border-slate-100 bg-slate-50/80 flex items-center justify-between">
              <div className="text-xs text-slate-500 font-medium flex items-center gap-1.5">
                2 biến thể <MaterialIcon name="shuffle" className="text-[14px]" /> random
              </div>
              <div className="flex items-center gap-3">
                <button className="px-6 py-2.5 text-sm font-bold text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors shadow-sm">
                  Hủy
                </button>
                <button className="px-6 py-2.5 text-sm font-bold text-white bg-blue-600 rounded-xl hover:bg-blue-700 transition-colors shadow-sm shadow-blue-600/20 flex items-center gap-2">
                  Tạo chiến dịch
                </button>
              </div>
            </div>
          </div>

          {/* Right Sidebar - Preview */}
          <div className="w-80 border-l border-slate-100 bg-[#f0f2f5] flex flex-col">
            <div className="p-4 border-b border-slate-200 bg-white">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">XEM TRƯỚC</h3>
                <span className="text-[10px] font-bold text-slate-400 flex items-center gap-1"><MaterialIcon name="shuffle" className="text-[12px]" /> Random</span>
              </div>
              <div className="flex gap-2">
                <button className="flex-1 py-1.5 bg-blue-600 text-white text-xs font-bold rounded-lg shadow-sm">Nội dung 1</button>
                <button className="flex-1 py-1.5 bg-white text-slate-600 border border-slate-200 text-xs font-bold rounded-lg hover:bg-slate-50 shadow-sm">Nội dung 2</button>
              </div>
            </div>
            
            <div className="flex-1 p-4 overflow-y-auto">
              {/* Fake chat preview */}
              <div className="flex gap-3 mb-4">
                <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white font-bold text-xs shrink-0 shadow-sm">Z</div>
                <div>
                  <h4 className="text-xs font-bold text-slate-700 mb-0.5">Nguyễn Văn A</h4>
                  <p className="text-[10px] text-slate-500 mb-2">Zalo</p>
                  <div className="bg-blue-600 text-white text-[13px] p-3 rounded-2xl rounded-tl-sm whitespace-pre-wrap shadow-sm leading-relaxed max-w-[220px]">
                    {content1.replace('{name}', 'Anh')}
                  </div>
                  <div className="flex gap-1 mt-1 max-w-[220px]">
                    <img src="https://picsum.photos/100" className="w-1/2 h-20 object-cover rounded-lg border border-slate-200" alt="p1"/>
                    <img src="https://picsum.photos/100?random=1" className="w-1/2 h-20 object-cover rounded-lg border border-slate-200" alt="p2"/>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="p-3 bg-white border-t border-slate-200 text-center">
              <p className="text-[10px] text-slate-500 font-medium">✨ Mỗi người nhận ngẫu nhiên 1 trong 2 nội dung</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
