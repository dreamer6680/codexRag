import { NextRequest, NextResponse } from "next/server";

import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const form = await request.formData();
    const file = form.get("file");

    if (!(file instanceof File)) {
      return NextResponse.json(
        { detail: "请选择文件" },
        { status: 400 },
      );
    }

    const upstreamForm = new FormData();
    upstreamForm.append("file", file, file.name);

    const response = await ragFetch("/rag/upload", {
      method: "POST",
      body: upstreamForm,
    });

    const payload = await response.json().catch(() => ({
      detail: "上传服务返回了无效响应",
    }));

    return NextResponse.json(payload, {
      status: response.status,
    });
  } catch {
    return NextResponse.json(
      { detail: "无法连接本地 RAG 上传服务" },
      { status: 503 },
    );
  }
}
