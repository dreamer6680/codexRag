"use client";

export type FilterDocument = { document_id: string; document_name: string; status: string };

export function DocumentFilter({ documents, selected, saving, onChange }: {
  documents: FilterDocument[];
  selected: string[];
  saving: boolean;
  onChange: (ids: string[]) => void;
}) {
  const ready = documents.filter(item => item.status === "ready");
  return <details className="relative">
    <summary className="list-none cursor-pointer rounded-md border bg-white px-3 py-2 text-sm font-medium hover:bg-zinc-50">{selected.length ? `已选 ${selected.length} 个文档` : "全部我的文档"}</summary>
    <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border bg-white p-4 shadow-xl">
      <div className="flex items-center justify-between"><p className="text-sm font-medium">本次聊天的检索范围</p>{saving && <span className="text-xs text-zinc-500">保存中…</span>}</div>
      <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm hover:bg-zinc-50">
        <input type="radio" checked={!selected.length} onChange={() => onChange([])} />全部我的已就绪文档
      </label>
      <div className="mt-2 max-h-56 space-y-1 overflow-y-auto border-t pt-2">
        {ready.map(document => <label key={document.document_id} className="flex cursor-pointer items-start gap-2 rounded-md p-2 text-sm hover:bg-zinc-50">
          <input type="checkbox" checked={selected.includes(document.document_id)} onChange={event => {
            const next = event.target.checked
              ? [...selected, document.document_id]
              : selected.filter(id => id !== document.document_id);
            onChange(next);
          }} />
          <span className="min-w-0 truncate">{document.document_name}</span>
        </label>)}
        {!ready.length && <p className="p-2 text-sm text-zinc-500">还没有已就绪文档。</p>}
      </div>
    </div>
  </details>;
}
