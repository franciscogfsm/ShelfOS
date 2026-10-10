# Deploying ShelfOS to the cloud

One container serves the model, the API and the web interface. The same image runs on a
laptop, on Hugging Face Spaces, Fly.io, Render, Railway or Google Cloud Run.

## 1. Build the release folder (once per model)

```
python run.py --train                 # only if labels or code changed
python tools/release.py               # builds the UI and gathers everything into release/
```

`release/` is self-contained: code, `models/engine.pkl`, backbone weights, planogram,
reference frames (shown in the app), the built UI, a `Dockerfile`, a Space `README.md` and a
`.gitattributes` for git-lfs. Nothing in it needs the network at run time.

Try it locally with Docker if you have it:

```
docker build -t shelfos release
docker run --rm -p 7860:7860 shelfos        # http://localhost:7860
```

## 2a. Hugging Face Spaces (free, simplest, public URL in ~10 min)

1. Create a Space at https://huggingface.co/new-space: SDK **Docker**, hardware **CPU basic**
   (2 vCPU, 16 GB RAM is enough; CPU upgrade makes analysis ~3x faster).
2. Push the release folder as the Space repository:

```
pip install -U "huggingface_hub[cli]"
huggingface-cli login                       # paste a write token
cd release
git init && git lfs install
git remote add origin https://huggingface.co/spaces/<user>/<space>
git add . && git commit -m "ShelfOS"
git push -u origin main --force
```

   Or without git: `huggingface-cli upload <user>/<space> release . --repo-type space`.
3. The Space builds the image (first time ~5 min). The app is at
   `https://<user>-<space>.hf.space`, the API at `/api/health` and `/docs`.

The first analysis after a cold start takes ~20 s (the backbone loads); after that an image is
answered in ~2-4 s on CPU basic.

## 2b. Fly.io (always-on, custom domain)

```
cd release
fly launch --no-deploy --name shelfos --vm-memory 4096   # accept the Dockerfile
fly deploy
```

Set `internal_port = 7860` in the generated `fly.toml` if it is not already.

## 2c. Render / Railway / Cloud Run

Point the service at the `release/` folder with its `Dockerfile`; set the port to **7860**
(or set the `PORT` env var, the container honours it); give it at least **4 GB RAM**.
Cloud Run: `gcloud run deploy shelfos --source release --memory 4Gi --cpu 2 --port 7860 --allow-unauthenticated`.

## Keeping the model out of git

`models/`, `cache/`, `data/` are git-ignored on purpose (they are rebuilt from the images and
labels). `release/` is the only place where model artefacts are committed, and only in the
deployment repo (Space), via git-lfs.

## Checks before the demo

```
python tools/selftest.py                      # awkward inputs still give complete answers
python run.py --images <folder or zip> --out predictions.json
python -m shelfos.validate predictions.json --images <folder or zip>   # official format, nothing missing
```
