"use client";

import { Button } from "@/components/ui/button";

export function DocumentDeleteDialog({ open, documentName, busy, onCancel, onConfirm }: {
  open: boolean;
  documentName: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!open) return null;
  return <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/45 p-4" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <section role="dialog" aria-modal="true" aria-labelledby="delete-document-title" className="w-full max-w-md rounded-xl border border-red-100 bg-white p-6 shadow-2xl">
      <p className="font-mono text-[11px] tracking-[.14em] text-red-600">IRREVERSIBLE DELETE</p>
      <h2 id="delete-document-title" className="mt-2 text-xl font-semibold">删除这份资料？</h2>
      <p className="mt-3 text-sm leading-6 text-zinc-600">原文件、解析内容和向量索引都会被清理，历史回答中的相关引用也会移除。此操作无法恢复。</p>
      <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-xs text-zinc-700">{documentName}</div>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="outline" disabled={busy} onClick={onCancel}>取消</Button>
        <Button disabled={busy} className="bg-red-600 text-white hover:bg-red-700" onClick={onConfirm}>{busy ? "正在删除…" : "确认删除"}</Button>
      </div>
    </section>
  </div>;
}
