"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChatPanel } from "@/components/chat-panel";
import { ChatSidebar } from "@/components/chat-sidebar";
import { DocumentDetailView, type DocumentDetail } from "@/components/document-detail-view";
import { appendPendingTurn, completePendingTurn, failPendingTurn, type ChatMessage, type ConversationDetail, type ConversationListItem } from "@/lib/chat-state";

type DocumentRecord = { document_id: string; document_name: string; version: number; content_type?: string | null; parser: string; status: "ready" | "index_failed"; page_count?: number | null; pdf_type?: string | null; chunk_count: number; created_at?: string | null; updated_at?: string | null };
type View = "chat" | "documents" | "detail";

async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("请先登录");
  }
  if (!response.ok) throw new Error(payload.detail || "请求失败");
  return payload as T;
}

export function Workspace() {
  const [view, setView] = useState<View>("chat");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const activeIdRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [filterSaving, setFilterSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);

  useEffect(() => {
    void Promise.all([loadDocuments(), jsonRequest<{ conversations: ConversationListItem[] }>("/api/conversations")])
      .then(([, payload]) => {
        setConversations(payload.conversations);
        if (payload.conversations[0]) void openConversation(payload.conversations[0].id);
      })
      .catch(error => setNotice(error instanceof Error ? error.message : "无法加载工作区"));
  }, []);

  async function loadDocuments() {
    const payload = await jsonRequest<{ documents: DocumentRecord[] }>("/api/documents");
    setDocuments(payload.documents || []);
  }

  function activate(id: string | null) {
    activeIdRef.current = id;
    setActiveId(id);
  }

  async function openConversation(id: string) {
    activate(id);
    setView("chat");
    setMessages([]);
    const payload = await jsonRequest<ConversationDetail>(`/api/conversations/${id}`);
    if (activeIdRef.current !== id) return;
    setMessages(payload.messages);
    setSelectedDocumentIds(payload.selected_document_ids);
  }

  async function createConversation(): Promise<ConversationListItem> {
    const item = await jsonRequest<ConversationListItem>("/api/conversations", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    setConversations(current => [item, ...current.filter(value => value.id !== item.id)]);
    activate(item.id);
    setMessages([]);
    setSelectedDocumentIds([]);
    setInput("");
    setView("chat");
    return item;
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || sending) return;
    const conversationId = activeId || (await createConversation()).id;
    const userTempId = `user-${crypto.randomUUID()}`;
    const assistantTempId = `assistant-${crypto.randomUUID()}`;
    const optimistic = appendPendingTurn(messages, { conversationId, question, userMessageId: userTempId, assistantMessageId: assistantTempId, createdAt: new Date().toISOString() });
    setMessages(optimistic.messages);
    setInput(optimistic.input);
    setSending(true);
    try {
      const payload = await jsonRequest<{ conversation: ConversationListItem; user_message: ChatMessage; assistant_message: ChatMessage }>(`/api/conversations/${conversationId}/messages`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) });
      setConversations(current => [payload.conversation, ...current.filter(item => item.id !== conversationId)]);
      if (activeIdRef.current === conversationId) setMessages(current => completePendingTurn(current, userTempId, assistantTempId, payload.user_message, payload.assistant_message));
    } catch (error) {
      if (activeIdRef.current === conversationId) setMessages(current => failPendingTurn(current, assistantTempId, error instanceof Error ? error.message : "发送失败"));
    } finally {
      if (activeIdRef.current === conversationId) setSending(false);
    }
  }

  async function saveFilter(ids: string[]) {
    const conversationId = activeId || (await createConversation()).id;
    const previous = selectedDocumentIds;
    setSelectedDocumentIds(ids);
    setFilterSaving(true);
    try {
      const result = await jsonRequest<ConversationDetail>(`/api/conversations/${conversationId}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ document_ids: ids }) });
      if (activeIdRef.current === conversationId) setSelectedDocumentIds(result.selected_document_ids);
    } catch (error) {
      setSelectedDocumentIds(previous);
      setNotice(error instanceof Error ? error.message : "无法保存文档范围");
    } finally {
      setFilterSaving(false);
    }
  }

  async function upload(file: File) {
    setUploading(true);
    setNotice(`正在解析 ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await jsonRequest<{ indexed_chunks: number }>("/api/documents/upload", { method: "POST", body: form });
      setNotice(`已完成解析并索引 ${result.indexed_chunks} 个内容分块`);
      await loadDocuments();
    } catch (error) {
      setNotice(error instanceof Error ? `上传失败：${error.message}` : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function openDocument(id: string) {
    try {
      setDetail(await jsonRequest<DocumentDetail>(`/api/documents/${id}`));
      setView("detail");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法读取文档");
    }
  }

  return <div className="min-h-screen bg-zinc-50 text-zinc-950">
    <ChatSidebar conversations={conversations} activeId={activeId} view={view} onNew={() => void createConversation()} onSelect={id => void openConversation(id)} onView={next => setView(next)} />
    <main className="lg:pl-72">
      <header className="flex min-h-16 items-center justify-between border-b bg-white px-5 sm:px-8"><span className="font-mono text-[11px] tracking-[.14em] text-zinc-500">PRIVATE / {view.toUpperCase()}</span><div className="flex items-center gap-3"><Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">个人空间</Badge><select value={activeId || ""} onChange={event => event.target.value && void openConversation(event.target.value)} className="max-w-40 rounded-md border bg-white px-2 py-1.5 text-xs lg:hidden"><option value="">选择历史聊天</option>{conversations.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div></header>
      <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8">
        {notice && <div className="mb-5 flex items-center justify-between rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900"><span>{notice}</span><button onClick={() => setNotice(null)} aria-label="关闭">×</button></div>}
        {view === "chat" && <ChatPanel messages={messages} input={input} sending={sending} documents={documents} selectedDocumentIds={selectedDocumentIds} filterSaving={filterSaving} onInput={setInput} onSend={send} onFilter={ids => void saveFilter(ids)} />}
        {view === "documents" && <DocumentsView documents={documents} uploading={uploading} onUpload={upload} onOpen={openDocument} />}
        {view === "detail" && <DocumentDetailView detail={detail} onBack={() => setView("documents")} />}
      </div>
    </main>
  </div>;
}

function DocumentsView({ documents, uploading, onUpload, onOpen }: { documents: DocumentRecord[]; uploading: boolean; onUpload: (file: File) => void; onOpen: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return <div><div className="flex items-end justify-between"><div><h1 className="text-3xl font-semibold tracking-tight">我的文档</h1><p className="mt-2 text-sm text-zinc-500">这里只有当前账户上传的资料。</p></div><Button variant="outline" disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "解析中…" : "上传资料"}</Button><input ref={input} className="hidden" type="file" accept=".pdf,.txt,.md" onChange={event => { const file = event.target.files?.[0]; if (file) onUpload(file); event.target.value = ""; }} /></div><Card className="mt-7 overflow-hidden"><div className="border-b px-5 py-4 text-sm font-medium">全部资料 <span className="text-zinc-500">{documents.length}</span></div>{documents.length ? <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="bg-zinc-50 text-xs text-zinc-500"><tr><th className="px-5 py-3">名称</th><th className="px-5 py-3">状态</th><th className="px-5 py-3">分块</th><th className="px-5 py-3">解析器</th><th /></tr></thead><tbody>{documents.map(document => <tr key={document.document_id} className="border-t"><td className="px-5 py-4 font-medium">{document.document_name}</td><td className="px-5 py-4">{document.status === "ready" ? "已就绪" : "索引失败"}</td><td className="px-5 py-4 text-zinc-500">{document.chunk_count}</td><td className="px-5 py-4 text-zinc-500">{document.parser}</td><td className="px-5 py-4 text-right"><Button variant="ghost" onClick={() => onOpen(document.document_id)}>查看</Button></td></tr>)}</tbody></table></div> : <div className="grid min-h-72 place-items-center text-center"><div><p className="font-medium">还没有个人文档</p><p className="mt-2 text-sm text-zinc-500">上传 PDF、TXT 或 Markdown 后即可开始检索。</p></div></div>}</Card></div>;
}
