"""Send exported prompts to the Gemini API instead of pasting them into the web chat.

  python3 stage3/run_gemini_api.py --folder stage3/web/shared --limit 2      try 2 batches first
  python3 stage3/run_gemini_api.py --folder stage3/web/shared                all the rest
  python3 stage3/run_gemini_api.py --folder stage3/paper_test/web --model gemini-3.8-flash

Reads <folder>/batches.json and each batch_NNN.txt; writes the reply to batch_NNN.answer.txt (the same
file you would paste into), so the usual --import-web reads it. A batch whose answer file is not empty
is skipped: stop and restart at any time. Each call also writes batch_NNN.api.json: the model asked for,
the model version that answered, the finish reason and the token counts (provenance; no key).
Settings: temperature 0, JSON reply, the longest reply the model allows. Server errors (429/500/503)
are retried with waits of 30 s to 4 min, 6 tries; then that batch is left empty and the run moves on.
The API key is read from .env (GEMINI_API_KEY) and never written anywhere.
"""
import argparse
import json
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
WAITS = [30, 60, 120, 240, 240]
LOCK = threading.Lock()
TOTAL = {"prompt": 0, "output": 0, "thinking": 0}


def env(name: str) -> str:
    for line in open(ROOT / ".env", encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        if k == name:
            return v.strip().strip('"').strip("'")
    raise SystemExit(f"{name} not found in .env")


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def call(model: str, prompt: str) -> dict:
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 65536}}
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": env("GEMINI_API_KEY")})
    with urllib.request.urlopen(req, timeout=900, context=ctx()) as r:
        return json.loads(r.read())


def run_one(folder: Path, name: str, model: str) -> str:
    ans = folder / f"{name}.answer.txt"
    prompt = (folder / f"{name}.txt").read_text(encoding="utf-8")
    for attempt in range(len(WAITS) + 1):
        t0 = time.time()
        try:
            r = call(model, prompt)
            break
        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"
            if e.code not in (429, 500, 502, 503, 504):
                return f"{name}: failed, not retried ({msg})"
        except Exception as e:
            msg = str(e)[:120]
        if attempt < len(WAITS):
            print(f"  {name}: {msg[:90]}; waiting {WAITS[attempt]} s (try {attempt + 1}/{len(WAITS) + 1})", flush=True)
            time.sleep(WAITS[attempt])
    else:
        return f"{name}: gave up after {len(WAITS) + 1} tries; left empty, rerun later"
    cand = (r.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    u = r.get("usageMetadata", {})
    meta = {"model_requested": model, "model_version": r.get("modelVersion"), "finish_reason": cand.get("finishReason"),
            "tokens": {"prompt": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount"), "thinking": u.get("thoughtsTokenCount")},
            "seconds": round(time.time() - t0), "settings": {"temperature": 0, "responseMimeType": "application/json"},
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (folder / f"{name}.api.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    if not text.strip():
        return f"{name}: empty reply (finish reason {cand.get('finishReason')}); left empty"
    ans.write_text(text, encoding="utf-8")
    with LOCK:
        TOTAL["prompt"] += u.get("promptTokenCount") or 0
        TOTAL["output"] += u.get("candidatesTokenCount") or 0
        TOTAL["thinking"] += u.get("thoughtsTokenCount") or 0
    cut = "" if cand.get("finishReason") == "STOP" else f" · finish reason {cand.get('finishReason')} (the import keeps its complete pairs)"
    return f"{name}: saved · {meta['model_version']} · {meta['tokens']['output']} output tokens · {meta['seconds']} s{cut}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="e.g. stage3/web/shared or stage3/paper_test/web")
    ap.add_argument("--model", default=None, help="default: GEMINI_MODEL in .env")
    ap.add_argument("--limit", type=int, default=0, help="only this many batches (to try first)")
    ap.add_argument("--workers", type=int, default=3, help="batches sent at the same time")
    a = ap.parse_args()
    folder = (ROOT / a.folder).resolve()
    model = a.model or env("GEMINI_MODEL")
    names = sorted(json.load(open(folder / "batches.json", encoding="utf-8")))
    todo = [n for n in names if not (folder / f"{n}.answer.txt").exists() or not (folder / f"{n}.answer.txt").read_text(encoding="utf-8").strip()]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(names)} batches in {a.folder} · {len(names) - len(todo) if not a.limit else 'some'} already answered · "
          f"sending {len(todo)} to {model}, {a.workers} at a time", flush=True)
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(run_one, folder, n, model): n for n in todo}
        for f in as_completed(futs):
            done += 1
            print(f"[{done}/{len(todo)} · {(time.time() - t0) / 60:.1f} min] {f.result()}", flush=True)
    print(f"Tokens this run: prompt {TOTAL['prompt']:,} · output {TOTAL['output']:,} · thinking {TOTAL['thinking']:,} "
          f"(check your Google AI Studio billing page for the cost)")
    print("Then import as usual, naming the model version shown above, e.g. "
          '--import-web "Gemini <version>, API, temp 0"')


if __name__ == "__main__":
    main()
