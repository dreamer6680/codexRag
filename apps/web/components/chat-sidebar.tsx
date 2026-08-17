"use client";

import { Button } from "@/components/ui/button";
import { signOut } from "@/app/login/actions";
import type { ConversationListItem } from "@/lib/chat-state";

export function ChatSidebar({
  conversations,
  activeId,
  view,
  onNew,
  onSelect,
  onView,
}: {
  conversations: ConversationListItem[];
  activeId: string | null;
  view: "chat" | "documents" | "detail";
  onNew: () => void;
  onSelect: (id: string) => void;
  onView: (view: "chat" | "documents") => void;
}) {
  return <aside className="border-b bg-zinc-950 text-white lg:fixed lg:inset-y-0 lg:w-72 lg:border-b-0 lg:border-r lg:border-white/10">
    <div className="flex h-full flex-col p-4">
      <button onClick={() => onView("chat")} className="flex items-center gap-3 px-2 py-1 text-lg font-semibold">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-white text-sm text-zinc-950">知</span>知见
      </button>
      <Button type="button" onClick={onNew} className="mt-6 w-full justify-start bg-white text-zinc-950 hover:bg-zinc-200">＋ 新建聊天</Button>
      <nav className="mt-5 grid grid-cols-2 gap-1 lg:grid-cols-1">
        <button onClick={() => onView("chat")} className={`rounded-md px-3 py-2 text-left text-sm ${view === "chat" ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5"}`}>知识问答</button>
        <button onClick={() => onView("documents")} className={`rounded-md px-3 py-2 text-left text-sm ${view !== "chat" ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5"}`}>我的文档</button>
      </nav>
      <div className="mt-7 hidden min-h-0 flex-1 lg:block">
        <p className="px-2 font-mono text-[10px] tracking-[.18em] text-zinc-500">CHAT HISTORY</p>
        <div className="mt-3 max-h-[calc(100vh-300px)] space-y-1 overflow-y-auto">
          {conversations.map(item => <button key={item.id} onClick={() => onSelect(item.id)} className={`w-full truncate rounded-md px-3 py-2.5 text-left text-sm ${activeId === item.id && view === "chat" ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white"}`}>{item.title}</button>)}
          {!conversations.length && <p className="px-3 py-3 text-sm leading-6 text-zinc-500">发送第一条问题后，聊天会保存在这里。</p>}
        </div>
      </div>
      <form action={signOut} className="mt-4 hidden border-t border-white/10 pt-4 lg:block"><button className="w-full rounded-md px-3 py-2 text-left text-sm text-zinc-400 hover:bg-white/5 hover:text-white">退出登录</button></form>
    </div>
  </aside>;
}
