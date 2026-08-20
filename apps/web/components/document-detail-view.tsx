"use client";

import React, { useEffect, useState } from "react";
import { DocumentMarkdown } from "./document-markdown";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

export type DocumentChunk = {
  index: number;
  text: string;
  page?: number | null;
  section?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  confidence?: number | null;
  chunk_type?: string | null;
  section_path?: string[];
  parent_context?: string | null;
  keywords?: string[];
  entities?: {
    companies?: string[];
    roles?: string[];
    projects?: string[];
    dates?: string[];
    people?: string[];
  };
  bbox?: { x0: number; y0: number; x1: number; y1: number } | null;
  parser_confidence?: number | null;
};

export type DocumentDetail = {
  document_id: string;
  document_name: string;
  version: number;
  content_type?: string | null;
  parser: string;
  status: "ready" | "index_failed";
  page_count?: number | null;
  pdf_type?: string | null;
  chunk_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  original_url: string;
  markdown: string;
  chunks: DocumentChunk[];
};

type MarkdownMode = "rendered" | "raw" | "chunk";

export function DocumentDetailView({ detail, onBack, onDelete, deleting }: { detail: DocumentDetail | null; onBack: () => void; onDelete: (detail: DocumentDetail) => void; deleting: boolean }) {
  const [selectedPosition, setSelectedPosition] = useState(0);
  const [mode, setMode] = useState<MarkdownMode>("rendered");

  useEffect(() => {
    setSelectedPosition(0);
    setMode("rendered");
  }, [detail?.document_id, detail?.version]);

  if (!detail) {
    return (
      <Card className="p-6">
        <p className="text-sm text-zinc-500">还没有选择文档。</p>
        <Button variant="outline" className="mt-4" onClick={onBack}>返回我的文档</Button>
      </Card>
    );
  }

  const selectedChunk = detail.chunks[selectedPosition];
  const isPdf = detail.content_type?.toLowerCase().includes("pdf") ?? false;
  const pageHash = selectedChunk?.page ? `#page=${selectedChunk.page}` : "";
  const sourceUrl = detail.original_url ? `${detail.original_url}${pageHash}` : "";
  const sourceType = detail.pdf_type ? pdfTypeLabel(detail.pdf_type) : fileType(detail.document_name);

  return (
    <div>
      <Button variant="ghost" className="px-0 text-zinc-500" onClick={onBack}>返回我的文档</Button>

      <div className="mt-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <p className="font-mono text-[11px] tracking-[.14em] text-blue-600">PARSE WORKBENCH</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">{detail.document_name}</h1>
          <p className="mt-2 text-sm text-zinc-500">v{detail.version} · {detail.parser}</p>
        </div>
        <div className="flex items-center gap-2"><Badge className={`${detail.status === "ready" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}>
          {detail.status === "ready" ? "已就绪" : "索引失败"}
        </Badge><Button variant="outline" className="border-red-200 text-red-700 hover:bg-red-50" disabled={deleting} onClick={() => onDelete(detail)}>{deleting ? "删除中…" : "删除资料"}</Button></div>
      </div>

      <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="内容分块" value={String(detail.chunk_count)} />
        <Metric label="页数" value={detail.page_count ? `${detail.page_count} 页` : "未记录"} />
        <Metric label="原文类型" value={sourceType} />
        <Metric label="当前定位" value={chunkLocation(selectedChunk)} />
      </div>

      <Card className="mt-5 overflow-hidden border-blue-100">
        <div className="border-b bg-white px-4 py-3">
          {detail.chunks.length ? (
            <div className="flex gap-2 overflow-x-auto pb-1" aria-label="文档 Chunk 导航">
              {detail.chunks.map((chunk, position) => (
                <button
                  key={`${chunk.index}-${position}`}
                  type="button"
                  aria-label={`查看 Chunk ${chunk.index + 1}`}
                  aria-pressed={selectedPosition === position}
                  onClick={() => setSelectedPosition(position)}
                  className={`min-w-28 rounded-md border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${selectedPosition === position ? "border-blue-300 bg-blue-50 shadow-sm" : "bg-white hover:bg-zinc-50"}`}
                >
                  <span className="block font-mono text-[10px] text-zinc-500">CHUNK {String(chunk.index + 1).padStart(2, "0")}</span>
                  <span className="mt-1 block truncate text-xs text-zinc-700">{chunkLocation(chunk)}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="py-1 text-sm text-zinc-500">该文档暂无可用 Chunk。</p>
          )}
        </div>

        <div className="grid min-h-[620px] xl:grid-cols-2">
          <section className="border-b bg-zinc-100 xl:border-b-0 xl:border-r">
            <div className="flex h-12 items-center justify-between border-b bg-white px-4">
              <h2 className="text-sm font-semibold">原文</h2>
              <span className="font-mono text-[10px] tracking-wider text-zinc-500">{isPdf ? "PDF VIEW" : "SOURCE TEXT"}</span>
            </div>
            {isPdf && sourceUrl ? (
              <iframe key={sourceUrl} title="原始 PDF" src={sourceUrl} className="h-[568px] w-full bg-white" />
            ) : (
              <pre className="h-[568px] overflow-auto whitespace-pre-wrap p-5 text-sm leading-7 text-zinc-700">{detail.markdown || "暂无原文内容。"}</pre>
            )}
          </section>

          <section className="bg-white">
            <div className="flex min-h-12 flex-col justify-between gap-2 border-b px-4 py-2 sm:flex-row sm:items-center">
              <h2 className="text-sm font-semibold">Markdown 解析</h2>
              <div className="flex rounded-md border bg-zinc-50 p-0.5 text-xs" aria-label="Markdown 查看模式">
                {([
                  ["rendered", "渲染视图"],
                  ["raw", "原始 Markdown"],
                  ["chunk", "当前 Chunk"],
                ] as const).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={mode === id}
                    onClick={() => setMode(id)}
                    className={`rounded px-2.5 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${mode === id ? "bg-white text-zinc-950 shadow-sm" : "text-zinc-500 hover:text-zinc-900"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-[568px] overflow-auto p-6" aria-label="Markdown 解析内容">
              {mode === "rendered" && <DocumentMarkdown markdown={detail.markdown} />}
              {mode === "raw" && (
                <pre className="whitespace-pre-wrap rounded-md bg-zinc-950 p-4 text-xs leading-6 text-zinc-100">{detail.markdown || "暂无 Markdown 内容。"}</pre>
              )}
              {mode === "chunk" && (
                selectedChunk ? (
                  <div>
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <p className="font-mono text-xs text-blue-600">
                        CHUNK {selectedChunk.index + 1} · {chunkLocation(selectedChunk)}
                      </p>
                      <Badge className="border-blue-200 bg-blue-50 text-blue-700">
                        {chunkTypeLabel(selectedChunk.chunk_type)}
                      </Badge>
                    </div>
                    <ChunkStructure chunk={selectedChunk} />
                    <div className="rounded-md border-l-2 border-blue-500 bg-blue-50 p-4 text-sm leading-7 text-blue-950">
                      {selectedChunk.text || "当前 Chunk 没有文本内容。"}
                    </div>
                  </div>
                ) : <p className="text-sm text-zinc-500">该文档暂无可用 Chunk。</p>
              )}
            </div>
          </section>
        </div>
      </Card>
    </div>
  );
}

function ChunkStructure({ chunk }: { chunk: DocumentChunk }) {
  const rows = [
    ["章节", chunk.section_path?.join(" / ") || chunk.parent_context],
    ["公司", chunk.entities?.companies?.join("、")],
    ["岗位", chunk.entities?.roles?.join("、")],
    ["项目", chunk.entities?.projects?.join("、")],
    ["时间", chunk.entities?.dates?.join("、")],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) return null;
  return (
    <dl className="mb-4 grid gap-2 rounded-md border bg-zinc-50 p-3 text-xs sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="flex gap-2">
          <dt className="shrink-0 text-zinc-500">{label}：</dt>
          <dd className="font-medium text-zinc-800">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function chunkTypeLabel(type?: string | null) {
  return ({
    resume_experience: "简历经历",
    heading: "标题",
    paragraph: "段落",
    list_item: "列表项",
    table_row: "表格行",
    code: "代码",
  } as Record<string, string>)[type || ""] || "内容块";
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{label}</p>
    </Card>
  );
}

function chunkLocation(chunk?: DocumentChunk) {
  if (!chunk) return "未定位";
  if (chunk.page) return `第 ${chunk.page} 页`;
  if (chunk.section) return chunk.section;
  if (chunk.char_start != null && chunk.char_end != null) return `${chunk.char_start}–${chunk.char_end}`;
  return "未定位";
}

function pdfTypeLabel(type: string) {
  return ({ TextBased: "文本型 PDF", Scanned: "扫描型 PDF", ImageBased: "图片型 PDF", Mixed: "混合型 PDF" } as Record<string, string>)[type] || type;
}

function fileType(name: string) {
  return name.split(".").pop()?.toUpperCase() || "文件";
}
