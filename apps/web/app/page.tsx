"use client";

import { FormEvent, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Citation = { document_id: string; document_name: string; version: number; page?: number; section?: string; excerpt: string; confidence: number };
type Result = { status: "answered" | "refused" | "unavailable"; answer: string; citations: Citation[]; reason?: string };
type View = "chat" | "documents" | "parsing" | "detail";
type DocumentRow = { type: string; name: string; version: string; time: string; status: string; chunks: number };
type PdfInspection = { pdf_type: "TextBased" | "Scanned" | "ImageBased" | "Mixed"; page_count: number; confidence: number; pages_needing_ocr: number[] };
type UploadResult = { document_id: string; document_name: string; version: number; indexed_chunks: number; parser: string; status: "ready"; inspection?: PdfInspection };

const initialDocuments: DocumentRow[] = [
  { type: "PDF", name: "产品需求管理规范.pdf", version: "v3", time: "昨天 17:42", status: "已就绪", chunks: 126 },
  { type: "DOCX", name: "2026 Q3 研发协作手册.docx", version: "v1", time: "6 分钟前", status: "解析中", chunks: 72 },
  { type: "PDF", name: "用户研究访谈纪要.pdf", version: "v2", time: "7 月 28 日", status: "已就绪", chunks: 84 },
  { type: "PPTX", name: "数据安全合规说明.pptx", version: "v1", time: "7 月 26 日", status: "解析失败", chunks: 0 },
];
const demoCitations: Citation[] = [
  { document_id: "prd", document_name: "产品需求管理规范.pdf", version: 3, page: 8, section: "需求评审", confidence: .95, excerpt: "评审小组由产品、研发、测试及业务代表组成。" },
  { document_id: "prd", document_name: "产品需求管理规范.pdf", version: 3, page: 10, section: "评审准备", confidence: .92, excerpt: "产品负责人应在会前提交 PRD、交互稿与成本评估。" },
];

function Status({ value }: { value: string }) {
  const styles = value === "已就绪" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : value === "解析中" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-red-200 bg-red-50 text-red-700";
  return <Badge className={styles}>{value}</Badge>;
}

export default function Home() {
  const [view, setView] = useState<View>("chat");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>({ status: "answered", answer: "按照当前的《产品需求管理规范》，需求评审至少应包含产品负责人、研发负责人、测试负责人和业务代表。若需求涉及数据采集或个人信息，还需要邀请安全与法务同事共同确认。\n\n评审开始前，产品负责人需要提交 PRD、交互稿和成本评估；会议结论应在两个工作日内同步至需求卡片。", citations: demoCitations });
  const [activeChunk, setActiveChunk] = useState(0);
  const [documents, setDocuments] = useState<DocumentRow[]>(initialDocuments);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [lastInspection, setLastInspection] = useState<PdfInspection | null>(null);

  async function uploadFile(file: File) {
    setUploading(true); setUploadMessage(`正在解析并索引 ${file.name}…`);
    try {
      const form = new FormData(); form.append("file", file);
      const response = await fetch("/api/documents/upload", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload);
        throw new Error(detail);
      }
      const result = payload as UploadResult;
      setLastInspection(result.inspection || null);
      setDocuments(current => [{ type: file.name.split(".").pop()?.toUpperCase() || "FILE", name: result.document_name, version: `v${result.version}`, time: "刚刚", status: "已就绪", chunks: result.indexed_chunks }, ...current]);
      const inspectionText = result.inspection ? ` PDF Inspector 判定为${pdfTypeLabel(result.inspection.pdf_type)}。` : "";
      const parserText = result.parser === "pdf-inspector" ? "已使用 PDF Inspector 快速提取，无需 MinerU OCR。" : `解析器：${result.parser}。`;
      setUploadMessage(`${result.document_name} 已完成解析，共索引 ${result.indexed_chunks} 个分块。${inspectionText} ${parserText}`);
      setView("documents");
    } catch (error) {
      setUploadMessage(error instanceof Error ? `上传失败：${error.message}` : "上传失败，请检查解析服务。 ");
    } finally { setUploading(false); }
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); if (!question.trim()) return;
    setLoading(true); setResult(null);
    try { const response = await fetch("/api/query", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) }); setResult(await response.json()); }
    catch { setResult({ status: "unavailable", answer: "无法连接本地 RAG 服务。请检查 Docker 服务状态。", citations: [] }); }
    finally { setLoading(false); }
  }

  const nav = [{ id: "chat" as View, label: "知识问答", mark: "01" }, { id: "documents" as View, label: "我的文档", mark: "02" }, { id: "parsing" as View, label: "解析任务", mark: "03" }];
  return <div className="min-h-screen bg-zinc-50 text-zinc-950">
    <aside className="fixed inset-y-0 hidden w-60 border-r bg-white p-4 lg:block">
      <button onClick={() => setView("chat")} className="flex items-center gap-2 px-2 text-lg font-semibold"><span className="grid h-7 w-7 place-items-center rounded-md bg-zinc-900 text-sm text-white">知</span>知见</button>
      <div className="mt-8 rounded-lg border bg-zinc-50 p-3"><p className="font-medium">产品研发知识库</p><p className="mt-1 text-xs text-muted-foreground">上海 · 26 位成员</p></div>
      <nav className="mt-6 grid gap-1">{nav.map(item => <button key={item.id} onClick={() => setView(item.id)} className={`flex items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors ${view === item.id || (view === "detail" && item.id === "parsing") ? "bg-zinc-100 font-medium" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950"}`}><span className="font-mono text-[11px] text-zinc-400">{item.mark}</span>{item.label}</button>)}</nav>
      <div className="absolute bottom-5 flex items-center gap-2 px-2"><span className="grid h-8 w-8 place-items-center rounded-full bg-amber-100 text-xs font-semibold text-amber-900">林</span><div className="text-xs"><p className="font-medium">林然</p><p className="text-muted-foreground">管理员</p></div></div>
    </aside>
    <main className="lg:pl-60"><header className="flex h-16 items-center justify-between border-b bg-white px-5 sm:px-8"><span className="font-mono text-[11px] tracking-wide text-muted-foreground">WORKSPACE / {view === "detail" ? "PARSING DETAIL" : view.toUpperCase()}</span><Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">● 检索服务正常</Badge></header>
      <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8">{view === "chat" && <Chat question={question} setQuestion={setQuestion} ask={ask} loading={loading} result={result} documents={documents} uploading={uploading} onUpload={uploadFile} />}{view === "documents" && <Documents documents={documents} uploadMessage={uploadMessage} inspection={lastInspection} uploading={uploading} onUpload={uploadFile} onDetail={() => setView("detail")} />}{view === "parsing" && <Parsing onDetail={() => setView("detail")} />}{view === "detail" && <Detail activeChunk={activeChunk} setActiveChunk={setActiveChunk} back={() => setView("documents")} />}</div>
    </main>
  </div>;
}

function Chat({ question, setQuestion, ask, loading, result, documents, uploading, onUpload }: { question: string; setQuestion: (value: string) => void; ask: (event: FormEvent) => void; loading: boolean; result: Result | null; documents: DocumentRow[]; uploading: boolean; onUpload: (file: File) => Promise<void> }) {
  return <><div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="font-mono text-xs text-blue-600">EVIDENCE-FIRST KNOWLEDGE WORK</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">把团队经验，变成可核验的答案。</h1></div><p className="max-w-xs text-sm leading-6 text-muted-foreground">答案只基于已授权资料生成；每一条结论都能回到原文。</p></div><div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]"><Card className="overflow-hidden"><div className="flex items-center justify-between border-b px-5 py-4 text-sm"><span className="text-muted-foreground">正在检索 <b className="text-foreground">全部已就绪资料</b> · {documents.filter(item => item.status === "已就绪").length} 个文档</span><Button variant="outline" className="h-8">筛选资料</Button></div><div className="min-h-[440px] space-y-7 p-5"><div className="ml-auto max-w-lg rounded-lg bg-zinc-100 p-4 text-sm"><p className="mb-1 text-xs text-muted-foreground">你</p>新版本的需求评审，需要哪些关键角色参加？</div>{loading && <div className="text-sm text-muted-foreground">正在检索、重排并核验证据…</div>}{result && <div className="max-w-2xl"><div className="mb-3 flex items-center gap-2 text-sm font-semibold"><span className="grid h-7 w-7 place-items-center rounded-md bg-zinc-900 text-white">知</span>知见助手</div><p className="whitespace-pre-line text-sm leading-7">{result.answer}</p>{result.citations.length > 0 && <div className="mt-5 border-l-2 border-emerald-500 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">✓ 检索到 {result.citations.length} 份直接依据，<b>回答置信度高</b></div>}</div>}</div><form onSubmit={ask} className="flex gap-2 border-t p-4"><Input value={question} onChange={e => setQuestion(e.target.value)} placeholder="在知识库中提问，例如：本季度的发布流程是什么？" /><Button disabled={loading}>{loading ? "检索中" : "发送 ↑"}</Button></form></Card><Sources citations={result?.citations || []} documents={documents} uploading={uploading} onUpload={onUpload} /></div></>;
}

function UploadButton({ uploading, onUpload, className = "" }: { uploading: boolean; onUpload: (file: File) => Promise<void>; className?: string }) { const input = useRef<HTMLInputElement>(null); return <><Button type="button" variant="outline" className={className} disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "正在解析…" : "＋ 上传资料"}</Button><input ref={input} className="hidden" type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" onChange={event => { const file = event.target.files?.[0]; if (file) void onUpload(file); event.target.value = ""; }} /></>; }

function Sources({ citations, documents, uploading, onUpload }: { citations: Citation[]; documents: DocumentRow[]; uploading: boolean; onUpload: (file: File) => Promise<void> }) { return <div className="space-y-5"><Card className="p-5"><h2 className="text-lg font-semibold">资料库</h2><UploadButton uploading={uploading} onUpload={onUpload} className="mt-4 w-full justify-start" /><div className="mt-4 space-y-3">{documents.slice(0, 2).map(doc => <div key={`${doc.name}-${doc.version}`} className="flex items-start gap-3"><span className="rounded border px-1.5 py-1 font-mono text-[10px] text-muted-foreground">{doc.type}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{doc.name}</p><p className="text-xs text-muted-foreground">{doc.version} · {doc.time}</p></div><Status value={doc.status} /></div>)}</div></Card><Card className="p-5"><div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">本次引用</h2><span className="font-mono text-[10px] text-blue-600">{citations.length} SOURCES</span></div>{citations.length ? citations.map((item, index) => <div key={index} className="border-l-2 border-blue-500 py-1 pl-3 not-last:mb-4"><p className="text-sm font-medium">[{index + 1}] {item.document_name}</p><p className="mt-1 text-xs text-muted-foreground">v{item.version} · 第 {item.page} 页 · {item.section}</p><p className="mt-2 text-xs leading-5 text-zinc-600">“{item.excerpt}”</p></div>) : <p className="text-sm text-muted-foreground">回答后会在这里显示可定位的原文证据。</p>}</Card></div>; }

function pdfTypeLabel(type: PdfInspection["pdf_type"]) { return ({ TextBased: "文本型 PDF", Scanned: "扫描型 PDF", ImageBased: "图片型 PDF", Mixed: "混合型 PDF" })[type]; }

function Documents({ documents, uploadMessage, inspection, uploading, onUpload, onDetail }: { documents: DocumentRow[]; uploadMessage: string | null; inspection: PdfInspection | null; uploading: boolean; onUpload: (file: File) => Promise<void>; onDetail: () => void }) { return <><div className="mb-7 flex items-end justify-between"><div><h1 className="text-3xl font-semibold tracking-tight">我的文档</h1><p className="mt-2 text-sm text-muted-foreground">资料完成解析后，才会加入问答检索范围。</p></div><UploadButton uploading={uploading} onUpload={onUpload} /></div>{uploadMessage && <div className={`mb-4 rounded-md border px-4 py-3 text-sm ${uploadMessage.startsWith("上传失败") ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-800"}`}>{uploadMessage}</div>}{inspection && <Card className="mb-5 border-blue-200 bg-blue-50/50 p-5"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><div className="flex items-center gap-2"><Badge className="border-blue-200 bg-white text-blue-700">PDF INSPECTOR</Badge><h2 className="font-semibold">本地 PDF 检查结果</h2></div><p className="mt-2 text-sm text-muted-foreground">Rust 引擎在上传代理中完成检测，文件不会发送给外部检查服务。</p></div><div className="grid grid-cols-3 gap-6 text-sm"><div><p className="text-xs text-muted-foreground">文档类型</p><p className="mt-1 font-medium">{pdfTypeLabel(inspection.pdf_type)}</p></div><div><p className="text-xs text-muted-foreground">页数 / 置信度</p><p className="mt-1 font-medium">{inspection.page_count} 页 · {Math.round(inspection.confidence * 100)}%</p></div><div><p className="text-xs text-muted-foreground">需要 OCR</p><p className="mt-1 font-medium">{inspection.pages_needing_ocr.length ? `第 ${inspection.pages_needing_ocr.join("、")} 页` : "无需 OCR"}</p></div></div></div></Card>}<Card className="overflow-hidden"><div className="border-b px-5 py-4 text-sm font-medium">全部资料 <span className="ml-1 text-muted-foreground">{documents.length}</span></div><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="bg-zinc-50 text-xs text-muted-foreground"><tr><th className="px-5 py-3 font-medium">文档名称</th><th className="px-5 py-3 font-medium">版本</th><th className="px-5 py-3 font-medium">解析状态</th><th className="px-5 py-3 font-medium">更新时间</th><th /></tr></thead><tbody>{documents.map(doc => <tr key={`${doc.name}-${doc.version}`} className="border-t"><td className="px-5 py-4"><span className="mr-3 font-mono text-[11px] text-muted-foreground">{doc.type}</span><span className="font-medium">{doc.name}</span></td><td className="px-5 py-4 text-muted-foreground">{doc.version}</td><td className="px-5 py-4"><Status value={doc.status} />{doc.status === "解析中" && <div className="mt-2 h-1.5 w-28 overflow-hidden rounded-full bg-zinc-100"><div className="h-full w-2/3 bg-blue-600" /></div>}</td><td className="px-5 py-4 text-muted-foreground">{doc.time}</td><td className="px-5 py-4"><Button variant="ghost" className="h-8" onClick={onDetail}>查看详情</Button></td></tr>)}</tbody></table></div></Card></> }

function Parsing({ onDetail }: { onDetail: () => void }) { return <><h1 className="text-3xl font-semibold tracking-tight">解析任务</h1><p className="mt-2 text-sm text-muted-foreground">跟踪文件提取、分块与向量索引的每一步。</p><div className="mt-7 grid gap-5 md:grid-cols-3">{[["18", "已完成文档"], ["1", "正在解析"], ["126", "当前文档分块"]].map(([value, label]) => <Card key={label} className="p-5"><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-sm text-muted-foreground">{label}</p></Card>)}</div><Card className="mt-5 p-5"><div className="flex items-center justify-between"><div><h2 className="font-semibold">2026 Q3 研发协作手册.docx</h2><p className="mt-1 text-sm text-muted-foreground">正在提取表格与正文内容，并建立检索索引。</p></div><Status value="解析中" /></div><div className="mt-5 h-2 overflow-hidden rounded-full bg-zinc-100"><div className="h-full w-2/3 bg-blue-600" /></div><div className="mt-5 flex justify-end"><Button variant="outline" onClick={onDetail}>查看分块详情</Button></div></Card></> }

const chunks = [["1. 文档目的与适用范围", "第 1 页", "428", "本规范明确产品需求的提出、评审、交付与复盘流程……"], ["2. 需求信息完整性", "第 2 页", "716", "需求提出前需提供业务背景、目标用户、预期收益与风险说明……"], ["3. 评审角色与职责", "第 3 页", "594", "评审小组由产品、研发、测试及业务代表组成……"]];
function Detail({ activeChunk, setActiveChunk, back }: { activeChunk: number; setActiveChunk: (value: number) => void; back: () => void }) { const chunk = chunks[activeChunk]; return <><Button variant="ghost" className="mb-5 px-0 text-muted-foreground" onClick={back}>← 返回资料库</Button><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><h1 className="text-3xl font-semibold tracking-tight">产品需求管理规范.pdf</h1><p className="mt-2 text-sm text-muted-foreground">v3 · 48 页 · 昨日 17:42 完成解析</p></div><Button variant="outline">重新解析</Button></div><div className="mt-7 grid gap-4 md:grid-cols-3"><Metric value="126" label="个内容分块" /><Metric value="标题层级 + 语义段落" label="分块策略" /><Metric value="612 字符 / 块" label="平均长度" /></div><div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]"><Card className="p-5"><div className="mb-5 flex items-start justify-between"><div><h2 className="text-lg font-semibold">内容分块</h2><p className="mt-1 text-sm text-muted-foreground">按照原文阅读顺序展示，可用于问答检索。</p></div><Button variant="outline">标题层级：全部</Button></div><div className="space-y-3">{chunks.map((item, index) => <button key={item[0]} onClick={() => setActiveChunk(index)} className={`w-full rounded-md border p-4 text-left transition-colors ${activeChunk === index ? "border-blue-200 bg-blue-50" : "hover:bg-zinc-50"}`}><p className="font-mono text-[11px] text-muted-foreground">分块 {String(index + 1).padStart(2, "0")} · {item[1]} · {item[2]} 字符</p><p className="mt-2 text-sm font-semibold">{item[0]}</p><p className="mt-1 text-sm text-muted-foreground">{item[3]}</p></button>)}</div></Card><Card className="p-5"><h2 className="text-lg font-semibold">原文定位</h2><p className="mt-1 text-sm text-muted-foreground">分块 {String(activeChunk + 1).padStart(2, "0")} · {chunk[1]}</p><div className="mt-5 min-h-80 rounded-md border bg-zinc-50 p-6"><p className="text-xs text-muted-foreground">产品需求管理规范</p><div className="my-4 h-px bg-zinc-200" /><p className="font-semibold">{chunk[0]}</p><p className="mt-4 rounded bg-blue-100 p-3 text-sm leading-6 text-blue-950">{chunk[3]}</p></div><p className="mt-3 text-xs text-muted-foreground">高亮区域为当前内容分块</p></Card></div></> }
function Metric({ value, label }: { value: string; label: string }) { return <Card className="p-5"><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-sm text-muted-foreground">{label}</p></Card> }
