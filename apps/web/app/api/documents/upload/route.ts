import { NextRequest, NextResponse } from "next/server";
import { processPdf } from "@firecrawl/pdf-inspector";
import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ detail: "请选择文件" }, { status: 400 });
    }
    let inspection: {
      pdf_type: string;
      page_count: number;
      confidence: number;
      pages_needing_ocr: number[];
    } | null = null;
    if (file.name.toLowerCase().endsWith(".pdf")) {
      try {
        const result = processPdf(Buffer.from(await file.arrayBuffer()));
        inspection = {
          pdf_type: result.pdfType,
          page_count: result.pageCount,
          confidence: result.confidence,
          // The package returns zero-based page indexes; expose human page numbers to the UI.
          pages_needing_ocr: result.pagesNeedingOcr.map(page => page + 1),
        };
      } catch {
        return NextResponse.json(
          { detail: "PDF Inspector 无法识别该文件，请确认它是未损坏的 PDF" },
          { status: 422 },
        );
      }
    }
    const upstreamForm = new FormData();
    upstreamForm.append("file", file, file.name);
    if (inspection) {
      upstreamForm.append("page_count", String(inspection.page_count));
      upstreamForm.append("pdf_type", inspection.pdf_type);
    }
    const response = await ragFetch("/rag/upload", {
      method: "POST",
      body: upstreamForm,
    });
    const payload = await response.json().catch(() => ({ detail: "上传服务返回了无效响应" }));
    return NextResponse.json(
      inspection && typeof payload === "object" && payload !== null
        ? { ...payload, inspection }
        : payload,
      { status: response.status },
    );
  } catch {
    return NextResponse.json({ detail: "无法连接本地 RAG 上传服务" }, { status: 503 });
  }
}
