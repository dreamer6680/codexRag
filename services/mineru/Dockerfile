# MinerU dependencies and model data should be pinned for the target CUDA/runtime.
# This wrapper keeps parsing local and provides a stable internal API.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-core fonts-noto-cjk fontconfig libgl1 \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8002
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
