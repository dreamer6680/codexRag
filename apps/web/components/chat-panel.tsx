"use client";

import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DocumentFilter, type FilterDocument } from "@/components/document-filter";
import type { ChatMessage } from "@/lib/chat-state";

export function ChatPanel({ messages, input, sending, documents, selectedDocumentIds, filterSaving, onInput, onSend, onFilter }: {
  messages: ChatMessage[];
  input: string;
  sending: boolean;
  documents: FilterDocument[];
  selectedDocumentIds: string[];
  filterSaving: boolean;
  onInput: (value: string) => void;
  onSend: (event: FormEvent) => void;
  onFilter: (ids: string[]) => void;
}) {
  return <div>
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="font-mono text-xs tracking-[.16em] text-blue-600">PERSONAL EVIDENCE THREAD</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">从自己的资料继续追问。</h1></div>
      <DocumentFilter documents={documents} selected={selectedDocumentIds} saving={filterSaving} onChange={onFilter} />
    </div>
    <Card className="overflow-hidden">
      <div className="min-h-[560px] space-y-6 p-5 sm:p-7">
        {!messages.length && <div className="grid min-h-[500px] place-items-center text-center"><div className="max-w-md"><span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-zinc-950 text-white">知</span><h2 className="mt-5 text-xl font-semibold">开始一段有记忆的问答</h2><p className="mt-2 text-sm leading-6 text-zinc-500">默认检索你的全部已就绪文档。后续问题会结合最近对话和长期摘要理解上下文。</p></div></div>}
        {messages.map(message => <article key={message.id} className={message.role === "user" ? "ml-auto max-w-2xl rounded-xl bg-zinc-100 p-4" : "max-w-3xl"}>
          <p className="mb-2 text-xs font-medium text-zinc-500">{message.role === "user" ? "你" : "知见助手"}</p>
          {message.status === "pending" ? <p className="text-sm text-zinc-500">正在检索个人资料并核验证据…</p> : message.status === "failed" ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{message.error || "回答失败，请重新发送问题"}</div> : <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p>}
          {message.citations?.length > 0 && <div className="mt-4 space-y-2 border-l-2 border-blue-500 pl-3">{message.citations.map((citation, index) => <details key={`${citation.document_id}-${index}`} className="text-xs"><summary className="cursor-pointer font-medium text-blue-700">[{index + 1}] {citation.document_name}{citation.page ? ` · 第 ${citation.page} 页` : ""}</summary><p className="mt-2 leading-5 text-zinc-600">{citation.excerpt}</p></details>)}</div>}
        </article>)}
      </div>
      <form onSubmit={onSend} className="flex gap-2 border-t bg-white p-4">
        <Input value={input} onChange={event => onInput(event.target.value)} disabled={sending} placeholder="继续提问，或引用上一条回答中的内容…" />
        <Button className="w-[100px]" disabled={sending || !input.trim()}>{sending ? "发送中" : "发送"}</Button>
      </form>
    </Card>
  </div>;
}
