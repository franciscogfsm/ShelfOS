# ShelfOS: model + API + web interface in one container (CPU).
#
#   python tools/release.py            # gathers model, planogram, reference frames and the built UI into release/
#   docker build -t shelfos .          # from the repo root (release/ must exist)
#   docker run -p 7860:7860 shelfos    # http://localhost:7860
#
# Works unchanged on Hugging Face Spaces (Docker SDK, port 7860), Fly.io, Render, Railway, Cloud Run.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=4 HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 PORT=7860

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch keeps the image at ~2.5 GB instead of ~8 GB.
RUN pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY shelfos ./shelfos
COPY run.py .
# everything the server needs at run time, assembled by tools/release.py
COPY release/models ./models
COPY release/data ./data
COPY release/web/out ./web/out

# a non-root user, as Hugging Face Spaces requires
RUN useradd -m -u 1000 shelf && chown -R shelf /app
USER shelf

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','7860'))"
CMD ["sh", "-c", "python run.py --lan --no-browser --cpu --port ${PORT}"]
