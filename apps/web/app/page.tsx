"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ConfidenceLevel, evidenceBanner } from "@/lib/query-presentation";

type Citation = { document_id: string; document_name: string; version: number; page?: number; section?: string; excerpt: string; confidence: number };
type Result = { status: "answered" | "refused" | "unavailable"; answer: string; citations: Citation[]; confidence: ConfidenceLevel; reason?: string };
type View = "chat" | "documents" | "parsing" | "detail";
type PdfInspection = { pdf_type: "TextBased" | "Scanned" | "ImageBased" | "Mixed"; page_count: number; confidence: number; pages_needing_ocr: number[] };
type UploadResult = { document_id: string; document_name: string; version: number; indexed_chunks: number; parser: string; status: "ready"; inspection?: PdfInspection };
type DocumentChunk = { index: number; page?: number | null; section?: string | null; text: string; char_start?: number | null; char_end?: number | null; confidence: number };
type DocumentRecord = {
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
};
type DocumentRow = DocumentRecord & { type: string; time: string };
type DocumentDetailData = DocumentRow & { original_url: string; markdown: string; chunks: DocumentChunk[] };

function Status({ value }: { value: string }) {
  const styles = value === "ready" || value === "已就绪"
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : value === "解析中"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : "border-red-200 bg-red-50 text-red-700";
  const label = value === "ready" ? "已就绪" : value === "index_failed" ? "索引失败" : value;
  return <Badge className={styles}>{label}</Badge>;
}

export default function Home() {
  const [view, setView] = useState<View>("chat");
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [activeChunk, setActiveChunk] = useState(0);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentDetailData | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [lastInspection, setLastInspection] = useState<PdfInspection | null>(null);

  async function loadDocuments() {
    try {
      const response = await fetch("/api/documents", { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json() as { documents?: DocumentRecord[] };
      const persistentRows = (payload.documents || []).map(recordToRow);
      setDocuments(persistentRows);
    } catch {
      setDocuments([]);
    }
  }

  useEffect(() => {
    void loadDocuments();
  }, []);

  async function uploadFile(file: File) {
    setUploading(true);
    setUploadMessage(`正在解析并索引 ${file.name}…`);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/documents/upload", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload);
        throw new Error(detail);
      }
      const upload = payload as UploadResult;
      setLastInspection(upload.inspection || null);
      const inspectionText = upload.inspection ? ` PDF Inspector 判定为${pdfTypeLabel(upload.inspection.pdf_type)}。` : "";
      const parserText = upload.parser === "pdf-inspector" ? "已使用 PDF Inspector 快速提取，无需 MinerU OCR。" : `解析器：${upload.parser}。`;
      setUploadMessage(`${upload.document_name} 已完成解析，共索引 ${upload.indexed_chunks} 个分块。${inspectionText} ${parserText}`);
      await loadDocuments();
      setView("documents");
    } catch (error) {
      setUploadMessage(error instanceof Error ? `上传失败：${error.message}` : "上传失败，请检查解析服务。");
    } finally {
      setUploading(false);
    }
  }

  async function openDetail(row: DocumentRow) {
    setActiveChunk(0);
    try {
      const response = await fetch(`/api/documents/${row.document_id}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "无法读取文档详情");
      setSelectedDocument({ ...recordToRow(payload), ...payload });
      setView("detail");
    } catch (error) {
      setUploadMessage(error instanceof Error ? `查看详情失败：${error.message}` : "查看详情失败。");
      setView("documents");
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const submitted = question.trim();
    if (!submitted) return;
    setSubmittedQuestion(submitted);
    setLoading(true);
    setResult(null);
    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: submitted }),
      });
      setResult(await response.json());
    } catch {
      setResult({ status: "unavailable", answer: "无法连接本地 RAG 服务。请检查 Docker 服务状态。", citations: [], confidence: "none" });
    } finally {
      setLoading(false);
    }
  }

  const nav = [
    { id: "chat" as View, label: "知识问答", mark: "01" },
    { id: "documents" as View, label: "我的文档", mark: "02" },
    { id: "parsing" as View, label: "解析任务", mark: "03" },
  ];

  return <div className="min-h-screen bg-zinc-50 text-zinc-950">
    <aside className="fixed inset-y-0 hidden w-60 border-r bg-white p-4 lg:block">
      <button onClick={() => setView("chat")} className="flex items-center gap-2 px-2 text-lg font-semibold">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-zinc-900 text-sm text-white">知</span>知见
      </button>
      <div className="mt-8 rounded-lg border bg-zinc-50 p-3">
        <p className="font-medium">产品研发知识库</p>
        <p className="mt-1 text-xs text-muted-foreground">本地解析 · 可追溯问答</p>
      </div>
      <nav className="mt-6 grid gap-1">
        {nav.map(item => <button key={item.id} onClick={() => setView(item.id)} className={`flex items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors ${view === item.id || (view === "detail" && item.id === "parsing") ? "bg-zinc-100 font-medium" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950"}`}>
          <span className="font-mono text-[11px] text-zinc-400">{item.mark}</span>{item.label}
        </button>)}
      </nav>
    </aside>
    <main className="lg:pl-60">
      <header className="flex h-16 items-center justify-between border-b bg-white px-5 sm:px-8">
        <span className="font-mono text-[11px] tracking-wide text-muted-foreground">WORKSPACE / {view === "detail" ? "PARSE DETAIL" : view.toUpperCase()}</span>
        <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">本地 RAG</Badge>
      </header>
      <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8">
        {view === "chat" && <Chat question={question} submittedQuestion={submittedQuestion} setQuestion={setQuestion} ask={ask} loading={loading} result={result} documents={documents} uploading={uploading} onUpload={uploadFile} />}
        {view === "documents" && <Documents documents={documents} uploadMessage={uploadMessage} inspection={lastInspection} uploading={uploading} onUpload={uploadFile} onDetail={openDetail} />}
        {view === "parsing" && <Parsing documents={documents} onDetail={openDetail} />}
        {view === "detail" && <Detail document={selectedDocument} activeChunk={activeChunk} setActiveChunk={setActiveChunk} back={() => setView("documents")} />}
      </div>
    </main>
  </div>;
}

function Chat({ question, submittedQuestion, setQuestion, ask, loading, result, documents, uploading, onUpload }: { question: string; submittedQuestion: string; setQuestion: (value: string) => void; ask: (event: FormEvent) => void; loading: boolean; result: Result | null; documents: DocumentRow[]; uploading: boolean; onUpload: (file: File) => Promise<void> }) {
  const banner = result ? evidenceBanner(result.confidence, result.citations.length) : null;
  return <>
    <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p className="font-mono text-xs text-blue-600">EVIDENCE-FIRST KNOWLEDGE WORK</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">把团队经验，变成可核验的答案。</h1>
      </div>
      <p className="max-w-xs text-sm leading-6 text-muted-foreground">答案只基于已授权资料生成；每一条结论都能回到原文。</p>
    </div>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b px-5 py-4 text-sm">
          <span className="text-muted-foreground">正在检索 <b className="text-foreground">全部已就绪资料</b> · {documents.filter(item => item.status === "ready").length} 个文档</span>
          <Button variant="outline" className="h-8">筛选资料</Button>
        </div>
        <div className="min-h-[440px] space-y-7 p-5">
          {submittedQuestion && <div className="ml-auto max-w-lg rounded-lg bg-zinc-100 p-4 text-sm">
            <p className="mb-1 text-xs text-muted-foreground">你</p>{submittedQuestion}
          </div>}
          {!submittedQuestion && !loading && !result && <div className="grid min-h-72 place-items-center text-center text-sm text-muted-foreground">输入问题后，系统会先检索并核验证据；没有可靠依据时会直接拒答。</div>}
          {loading && <div className="text-sm text-muted-foreground">正在检索、重排并核验证据…</div>}
          {result && <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><span className="grid h-7 w-7 place-items-center rounded-md bg-zinc-900 text-white">知</span>知见助手</div>
            <p className="whitespace-pre-line text-sm leading-7">{result.answer}</p>
            {banner && <div className={`mt-5 border-l-2 px-3 py-2 text-xs ${banner.className}`}>{banner.label}</div>}
          </div>}
        </div>
        <form onSubmit={ask} className="flex gap-2 border-t p-4">
          <Input value={question} onChange={e => setQuestion(e.target.value)} placeholder="在知识库中提问，例如：本季度的发布流程是什么？" />
          <Button disabled={loading}>{loading ? "检索中" : "发送"}</Button>
        </form>
      </Card>
      <Sources citations={result?.citations || []} documents={documents} uploading={uploading} onUpload={onUpload} />
    </div>
  </>;
}

function UploadButton({ uploading, onUpload, className = "" }: { uploading: boolean; onUpload: (file: File) => Promise<void>; className?: string }) {
  const input = useRef<HTMLInputElement>(null);
  return <>
    <Button type="button" variant="outline" className={className} disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "正在解析…" : "上传资料"}</Button>
    <input ref={input} className="hidden" type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" onChange={event => { const file = event.target.files?.[0]; if (file) void onUpload(file); event.target.value = ""; }} />
  </>;
}

function Sources({ citations, documents, uploading, onUpload }: { citations: Citation[]; documents: DocumentRow[]; uploading: boolean; onUpload: (file: File) => Promise<void> }) {
  return <div className="space-y-5">
    <Card className="p-5">
      <h2 className="text-lg font-semibold">资料库</h2>
      <UploadButton uploading={uploading} onUpload={onUpload} className="mt-4 w-full justify-start" />
      <div className="mt-4 space-y-3">{documents.length ? documents.slice(0, 2).map(doc => <DocumentMini key={doc.document_id} doc={doc} />) : <p className="text-sm text-muted-foreground">还没有已入库文档。</p>}</div>
    </Card>
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">本次引用</h2>
        <span className="font-mono text-[10px] text-blue-600">{citations.length} SOURCES</span>
      </div>
      {citations.length ? citations.map((item, index) => <div key={index} className="mb-4 border-l-2 border-blue-500 py-1 pl-3 last:mb-0">
        <p className="text-sm font-medium">[{index + 1}] {item.document_name}</p>
        <p className="mt-1 text-xs text-muted-foreground">v{item.version} · 第 {item.page || "-"} 页 · {item.section}</p>
        <p className="mt-2 text-xs leading-5 text-zinc-600">“{item.excerpt}”</p>
      </div>) : <p className="text-sm text-muted-foreground">回答后会在这里显示可定位的原文证据。</p>}
    </Card>
  </div>;
}

function DocumentMini({ doc }: { doc: DocumentRow }) {
  return <div className="flex items-start gap-3">
    <span className="rounded border px-1.5 py-1 font-mono text-[10px] text-muted-foreground">{doc.type}</span>
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm font-medium">{doc.document_name}</p>
      <p className="text-xs text-muted-foreground">v{doc.version} · {doc.time}</p>
    </div>
    <Status value={doc.status} />
  </div>;
}

function Documents({ documents, uploadMessage, inspection, uploading, onUpload, onDetail }: { documents: DocumentRow[]; uploadMessage: string | null; inspection: PdfInspection | null; uploading: boolean; onUpload: (file: File) => Promise<void>; onDetail: (row: DocumentRow) => void }) {
  return <>
    <div className="mb-7 flex items-end justify-between">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">我的文档</h1>
        <p className="mt-2 text-sm text-muted-foreground">资料完成解析后，会保留原文、Markdown 和分块索引。</p>
      </div>
      <UploadButton uploading={uploading} onUpload={onUpload} />
    </div>
    {uploadMessage && <div className={`mb-4 rounded-md border px-4 py-3 text-sm ${uploadMessage.startsWith("上传失败") || uploadMessage.startsWith("查看详情失败") ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-800"}`}>{uploadMessage}</div>}
    {inspection && <InspectionCard inspection={inspection} />}
    <Card className="overflow-hidden">
      <div className="border-b px-5 py-4 text-sm font-medium">全部资料 <span className="ml-1 text-muted-foreground">{documents.length}</span></div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[780px] text-left text-sm">
          <thead className="bg-zinc-50 text-xs text-muted-foreground">
            <tr><th className="px-5 py-3 font-medium">文档名称</th><th className="px-5 py-3 font-medium">版本</th><th className="px-5 py-3 font-medium">解析状态</th><th className="px-5 py-3 font-medium">分块</th><th className="px-5 py-3 font-medium">更新时间</th><th /></tr>
          </thead>
          <tbody>{documents.map(doc => <tr key={doc.document_id} className="border-t">
            <td className="px-5 py-4"><span className="mr-3 font-mono text-[11px] text-muted-foreground">{doc.type}</span><span className="font-medium">{doc.document_name}</span></td>
            <td className="px-5 py-4 text-muted-foreground">v{doc.version}</td>
            <td className="px-5 py-4"><Status value={doc.status} /></td>
            <td className="px-5 py-4 text-muted-foreground">{doc.chunk_count}</td>
            <td className="px-5 py-4 text-muted-foreground">{doc.time}</td>
            <td className="px-5 py-4"><Button variant="ghost" className="h-8" onClick={() => onDetail(doc)}>查看详情</Button></td>
          </tr>)}</tbody>
        </table>
      </div>
    </Card>
  </>;
}

function InspectionCard({ inspection }: { inspection: PdfInspection }) {
  return <Card className="mb-5 border-blue-200 bg-blue-50/50 p-5">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
      <div>
        <div className="flex items-center gap-2"><Badge className="border-blue-200 bg-white text-blue-700">PDF INSPECTOR</Badge><h2 className="font-semibold">本地 PDF 检查结果</h2></div>
        <p className="mt-2 text-sm text-muted-foreground">检查结果会随文档详情保存，用于原文对比和解析追踪。</p>
      </div>
      <div className="grid grid-cols-3 gap-6 text-sm">
        <MetricInline label="文档类型" value={pdfTypeLabel(inspection.pdf_type)} />
        <MetricInline label="页数 / 置信度" value={`${inspection.page_count} 页 · ${Math.round(inspection.confidence * 100)}%`} />
        <MetricInline label="需要 OCR" value={inspection.pages_needing_ocr.length ? `第 ${inspection.pages_needing_ocr.join("、")} 页` : "无需 OCR"} />
      </div>
    </div>
  </Card>;
}

function Parsing({ documents, onDetail }: { documents: DocumentRow[]; onDetail: (row: DocumentRow) => void }) {
  const ready = documents.filter(doc => doc.status === "ready");
  const latest = ready[0];
  return <>
    <h1 className="text-3xl font-semibold tracking-tight">解析任务</h1>
    <p className="mt-2 text-sm text-muted-foreground">跟踪文件提取、分块与向量索引的每一步。</p>
    <div className="mt-7 grid gap-5 md:grid-cols-3">
      <Metric value={String(ready.length)} label="已完成文档" />
      <Metric value={String(documents.reduce((sum, doc) => sum + doc.chunk_count, 0))} label="累计分块" />
      <Metric value={latest?.parser || "暂无"} label="最近解析器" />
    </div>
    {latest ? <Card className="mt-5 p-5">
      <div className="flex items-center justify-between">
        <div><h2 className="font-semibold">{latest.document_name}</h2><p className="mt-1 text-sm text-muted-foreground">可查看原始文件、解析 Markdown 与向量分块。</p></div>
        <Status value={latest.status} />
      </div>
      <div className="mt-5 flex justify-end"><Button variant="outline" onClick={() => onDetail(latest)}>查看解析详情</Button></div>
    </Card> : <Card className="mt-5 p-6 text-sm text-muted-foreground">还没有已完成的解析任务。</Card>}
  </>;
}

function Detail({ document, activeChunk, setActiveChunk, back }: { document: DocumentDetailData | null; activeChunk: number; setActiveChunk: (value: number) => void; back: () => void }) {
  const [mode, setMode] = useState<"rendered" | "raw" | "chunk">("rendered");
  if (!document) {
    return <Card className="p-6"><p className="text-sm text-muted-foreground">还没有选择文档。</p><Button variant="outline" className="mt-4" onClick={back}>返回资料库</Button></Card>;
  }
  const chunk = document.chunks[activeChunk] || document.chunks[0];
  const isPdf = document.content_type?.includes("pdf");
  const pageHash = chunk?.page ? `#page=${chunk.page}` : "";
  const originalSrc = document.original_url ? `${document.original_url}${pageHash}` : "";

  return <>
    <Button variant="ghost" className="mb-5 px-0 text-muted-foreground" onClick={back}>返回资料库</Button>
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
      <div>
        <p className="font-mono text-xs text-blue-600">PARSE WORKBENCH</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{document.document_name}</h1>
        <p className="mt-2 text-sm text-muted-foreground">v{document.version} · {document.parser} · {document.time}</p>
      </div>
      <Status value={document.status} />
    </div>
    <div className="mt-7 grid gap-4 md:grid-cols-4">
      <Metric value={String(document.chunk_count)} label="内容分块" />
      <Metric value={document.page_count ? `${document.page_count} 页` : "未记录"} label="页数" />
      <Metric value={document.pdf_type ? pdfTypeLabel(document.pdf_type) : document.type} label="原文类型" />
      <Metric value={chunk?.page ? `第 ${chunk.page} 页` : chunk?.section || "chars"} label="当前定位" />
    </div>
    <Card className="mt-5 overflow-hidden border-blue-100">
      <div className="border-b bg-white px-4 py-3">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {document.chunks.map(item => <button key={item.index} onClick={() => setActiveChunk(item.index)} className={`min-w-28 rounded-md border px-3 py-2 text-left transition-colors ${activeChunk === item.index ? "border-blue-300 bg-blue-50 shadow-sm" : "bg-white hover:bg-zinc-50"}`}>
            <span className="block font-mono text-[10px] text-zinc-500">chunk {String(item.index + 1).padStart(2, "0")}</span>
            <span className="mt-1 block truncate text-xs text-zinc-700">{item.page ? `第 ${item.page} 页` : charSpan(item)}</span>
          </button>)}
        </div>
      </div>
      <div className="grid min-h-[620px] xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="border-b bg-zinc-100 xl:border-b-0 xl:border-r">
          <div className="flex h-12 items-center justify-between border-b bg-white px-4">
            <h2 className="text-sm font-semibold">原文</h2>
            <span className="font-mono text-[11px] text-muted-foreground">{isPdf ? "PDF VIEW" : "SOURCE TEXT"}</span>
          </div>
          {isPdf && originalSrc ? <iframe title="原始 PDF" src={originalSrc} className="h-[568px] w-full bg-white" /> : <pre className="h-[568px] overflow-auto whitespace-pre-wrap p-5 text-sm leading-7 text-zinc-700">{document.markdown}</pre>}
        </section>
        <section className="bg-white">
          <div className="flex h-12 items-center justify-between border-b px-4">
            <h2 className="text-sm font-semibold">Markdown 解析</h2>
            <div className="flex rounded-md border bg-zinc-50 p-0.5 text-xs">
              {[
                ["rendered", "渲染视图"],
                ["raw", "原始 Markdown"],
                ["chunk", "当前 chunk"],
              ].map(([id, label]) => <button key={id} onClick={() => setMode(id as typeof mode)} className={`rounded px-2.5 py-1.5 ${mode === id ? "bg-white shadow-sm" : "text-muted-foreground"}`}>{label}</button>)}
            </div>
          </div>
          <div className="h-[568px] overflow-auto p-6">
            {mode === "rendered" && <div className="space-y-4 text-sm leading-7">{renderMarkdown(document.markdown)}</div>}
            {mode === "raw" && <pre className="whitespace-pre-wrap rounded-md bg-zinc-950 p-4 text-xs leading-6 text-zinc-100">{document.markdown}</pre>}
            {mode === "chunk" && <div><p className="mb-3 font-mono text-xs text-blue-600">{chunk ? `chunk ${chunk.index + 1} · ${chunk.section || charSpan(chunk)}` : "chunk"}</p><div className="rounded-md border-l-2 border-blue-500 bg-blue-50 p-4 text-sm leading-7 text-blue-950">{chunk?.text || "暂无分块内容"}</div></div>}
          </div>
        </section>
      </div>
    </Card>
  </>;
}

function renderMarkdown(markdown: string): ReactNode[] {
  const lines = markdown.split(/\r?\n/);
  const nodes: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index++;
      continue;
    }
    if (line.startsWith("```")) {
      const code: string[] = [];
      index++;
      while (index < lines.length && !lines[index].startsWith("```")) code.push(lines[index++]);
      index++;
      nodes.push(<pre key={nodes.length} className="overflow-auto rounded-md bg-zinc-950 p-4 text-xs leading-6 text-zinc-100"><code>{code.join("\n")}</code></pre>);
      continue;
    }
    if (line.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) {
      const tableLines = [line];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) tableLines.push(lines[index++]);
      nodes.push(renderTable(tableLines, nodes.length));
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      const className = level === 1 ? "text-2xl font-semibold" : level === 2 ? "text-xl font-semibold" : "text-base font-semibold";
      nodes.push(<div key={nodes.length} className={className}>{inlineMarkdown(heading[2])}</div>);
      index++;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) items.push(lines[index++].replace(/^[-*]\s+/, ""));
      nodes.push(<ul key={nodes.length} className="list-disc space-y-1 pl-5">{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</ul>);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) items.push(lines[index++].replace(/^\d+\.\s+/, ""));
      nodes.push(<ol key={nodes.length} className="list-decimal space-y-1 pl-5">{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</ol>);
      continue;
    }
    if (line.startsWith(">")) {
      nodes.push(<blockquote key={nodes.length} className="border-l-2 border-amber-400 bg-amber-50 px-4 py-2 text-amber-950">{inlineMarkdown(line.replace(/^>\s?/, ""))}</blockquote>);
      index++;
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      nodes.push(<hr key={nodes.length} className="border-zinc-200" />);
      index++;
      continue;
    }
    nodes.push(<p key={nodes.length} className="text-zinc-700">{inlineMarkdown(line)}</p>);
    index++;
  }
  return nodes.length ? nodes : [<p key="empty" className="text-sm text-muted-foreground">暂无 Markdown 内容。</p>];
}

function renderTable(lines: string[], key: number) {
  const rows = lines.map(line => line.trim().replace(/^\||\|$/g, "").split("|").map(cell => cell.trim()));
  const [head, ...body] = rows;
  return <div key={key} className="overflow-x-auto rounded-md border">
    <table className="w-full text-left text-sm">
      <thead className="bg-zinc-50"><tr>{head.map((cell, index) => <th key={index} className="border-b px-3 py-2 font-medium">{inlineMarkdown(cell)}</th>)}</tr></thead>
      <tbody>{body.map((row, rowIndex) => <tr key={rowIndex} className="border-b last:border-0">{row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-2">{inlineMarkdown(cell)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

function inlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index} className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <span key={index}>{part}</span>;
  });
}

function Metric({ value, label }: { value: string; label: string }) {
  return <Card className="p-5"><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-sm text-muted-foreground">{label}</p></Card>;
}

function MetricInline({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-medium">{value}</p></div>;
}

function pdfTypeLabel(type: string) {
  return ({ TextBased: "文本型 PDF", Scanned: "扫描型 PDF", ImageBased: "图片型 PDF", Mixed: "混合型 PDF" } as Record<string, string>)[type] || type;
}

function recordToRow(record: DocumentRecord): DocumentRow {
  return {
    ...record,
    type: record.document_name.split(".").pop()?.toUpperCase() || "FILE",
    time: formatTime(record.updated_at || record.created_at),
  };
}

function formatTime(value?: string | null) {
  if (!value) return "刚刚";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return date.toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function charSpan(chunk: DocumentChunk) {
  if (chunk.char_start == null || chunk.char_end == null) return chunk.section || "未定位";
  return `${chunk.char_start}-${chunk.char_end}`;
}
