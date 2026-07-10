# ManhwaManiacs backend — FastAPI on uvicorn (:8000), non-root.
# This container is internal-only: the frontend proxies /api/* to it over the
# per-environment private compose network. Persistent state (SQLite DB +
# downloaded pages) lives on the mounted /data volume via MM_DB_PATH /
# MM_DOWNLOADS_PATH so it survives image rebuilds.

FROM python:3.13-slim AS run
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# tesseract-ocr is the only system dependency (pytesseract shells out to it).
# Everything else ships as manylinux wheels (curl_cffi bundles its own libcurl).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Non-root, with a writable data dir for the DB + downloads.
RUN useradd -u 1000 -m app \
    && mkdir -p /data/downloads \
    && chown -R app:app /data /app
USER app

ENV MM_DB_PATH=/data/manhwamaniacs.db \
    MM_DOWNLOADS_PATH=/data/downloads

EXPOSE 8000
CMD ["python", "main.py"]
