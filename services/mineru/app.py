import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Local MinerU adapter")


@app.get("/health")
def health():
    executable = shutil.which("mineru")
    if not executable:
        raise HTTPException(503, "MinerU CLI is not installed")
    return {
        "status": "ok",
        "device": os.getenv("MINERU_DEVICE", "auto"),
        "model_source": os.getenv("MINERU_MODEL_SOURCE", "modelscope"),
        "executable": executable,
    }


@app.post("/parse")
async def parse(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "MinerU adapter currently accepts PDF files")
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / file.filename
        source.write_bytes(await file.read())
        output = Path(temporary) / "output"
        # MinerU stays inside the container. The pipeline backend works on CPU
        # and can use CUDA automatically when the runtime exposes a GPU.
        process = subprocess.run(
            ["mineru", "-p", str(source), "-o", str(output), "-b", "pipeline"],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if process.returncode != 0:
            raise HTTPException(422, {"message": "MinerU parse failed", "detail": process.stderr[-1000:]})
        markdown = next(output.rglob("*.md"), None)
        if not markdown:
            raise HTTPException(422, "MinerU produced no Markdown")
        return {"markdown": markdown.read_text(encoding="utf-8"), "source": file.filename, "confidence": "review_required"}
