"""
Backend per la valutazione di coppie di video.

Ogni coppia = un video "mine" (generato col prompt della tesi) e un video "base".
L'utente vede solo "Video A" / "Video B", in ordine casuale, e non sa quale sia
quale. Il backend calcola a quale sistema corrisponde ogni scelta e inoltra il
voto a un Google Sheet (via Google Apps Script).
"""

import json
import logging
import os
import random
import threading
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / "videos"
PAIRS_FILE = BASE_DIR / "pairs.json"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# ogni voto viene scritto qui prima di rispondere al
# client. I voti che non riescono a raggiungere il Google Sheet finiscono in
# VOTES_UNSYNCED_FILE per un reinvio.
VOTES_FILE = BASE_DIR / "votes.jsonl"
VOTES_UNSYNCED_FILE = BASE_DIR / "votes_unsynced.jsonl"

SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL", "").strip()
SHEET_TIMEOUT = 30          
SHEET_RETRIES = 3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("video-eval")

# Serializza le chiamate ad Apps Script
_sheet_lock = threading.Lock()
# Protegge le append ai file di log dei voti.
_file_lock = threading.Lock()

app = FastAPI(title="Video Evaluation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_pairs():
    with open(PAIRS_FILE, encoding="utf-8") as f:
        return json.load(f)["pairs"]


def _append_jsonl(path: Path, payload: dict):
    line = json.dumps(payload, ensure_ascii=False)
    with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def send_to_sheet(payload: dict):
    """
    Inoltra un voto al Google Sheet. Le chiamate ad
    Apps Script sono serializzate (vedi _sheet_lock) perché non regge bene la
    concorrenza. Solleva l'ultima eccezione se tutti i tentativi falliscono.
    """
    if not SHEET_WEBHOOK_URL:
        raise RuntimeError("SHEET_WEBHOOK_URL non configurato")
    data = json.dumps(payload).encode("utf-8")

    last_err = None
    for attempt in range(1, SHEET_RETRIES + 1):
        try:
            req = urllib.request.Request(
                SHEET_WEBHOOK_URL,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _sheet_lock:
                with urllib.request.urlopen(req, timeout=SHEET_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8")
            result = json.loads(body)
            if not result.get("ok"):
                raise RuntimeError(f"Sheet ha risposto con errore: {result}")
            return
        except Exception as e:  # retray su qualsiasi errore
            last_err = e
            logger.warning("Invio al Sheet fallito (tentativo %d/%d): %s",
                           attempt, SHEET_RETRIES, e)
            if attempt < SHEET_RETRIES:
                time.sleep(min(2 ** attempt, 8))
    raise last_err


def forward_to_sheet(payload: dict):
    """Task in background: inoltra al Sheet e, se fallisce, non perde il voto."""
    try:
        send_to_sheet(payload)
    except Exception as e:  # noqa: BLE001
        logger.error("Voto non inoltrato al Sheet, salvato in %s: %s",
                     VOTES_UNSYNCED_FILE.name, e)
        try:
            _append_jsonl(VOTES_UNSYNCED_FILE, payload)
        except Exception:  # noqa: BLE001
            logger.exception("Impossibile scrivere il voto non sincronizzato")


# ---------------------------------------------------------------------------
# Modelli richiesta
# ---------------------------------------------------------------------------

class VoteIn(BaseModel):
    session_id: str
    concept: str
    system_A: str            # 'mine' | 'base'
    system_B: str
    preference: str          # 'A' | 'B' | 'tie'
    relevance: str
    quality: str


# ---------------------------------------------------------------------------
# Endpoint API
# ---------------------------------------------------------------------------

@app.get("/api/session")
def new_session():
    """
    Crea una nuova sessione. Ritorna le coppie in ordine casuale; per ognuna
    A e B sono assegnati casualmente a 'mine'/'base'. Il client mostra solo
    Video A / Video B.
    """
    pairs = load_pairs()
    session_id = str(uuid.uuid4())
    order = pairs[:]
    random.shuffle(order)

    items = []
    for p in order:
        if random.random() < 0.5:
            system_A, system_B = "mine", "base"
            video_A, video_B = p["mine"], p["base"]
        else:
            system_A, system_B = "base", "mine"
            video_A, video_B = p["base"], p["mine"]

        item = {
            "concept": p["concept"],
            "label": p["label"],
            "video_A": f"/videos/{video_A}",
            "video_B": f"/videos/{video_B}",
            "system_A": system_A,
            "system_B": system_B,
        }
        if p.get("reference"):
            item["reference"] = f"/videos/{p['reference']}"
            item["reference_caption"] = p.get("reference_caption", "")
        items.append(item)

    return {"session_id": session_id, "items": items}


@app.post("/api/vote")
def submit_vote(vote: VoteIn, background: BackgroundTasks):
    if vote.system_A not in ("mine", "base") or vote.system_B not in ("mine", "base"):
        raise HTTPException(400, "system_A/system_B non validi")

    def to_system(choice: str) -> str:
        if choice == "A":
            return vote.system_A
        if choice == "B":
            return vote.system_B
        if choice == "tie":
            return "tie"
        raise HTTPException(400, f"scelta non valida: {choice}")

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": vote.session_id,
        "concept": vote.concept,
        "system_A": vote.system_A,
        "system_B": vote.system_B,
        "preference": vote.preference,
        "relevance": vote.relevance,
        "quality": vote.quality,
        "preferred_system": to_system(vote.preference),
        "relevance_system": to_system(vote.relevance),
        "quality_system": to_system(vote.quality),
    }

    try:
        _append_jsonl(VOTES_FILE, payload)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Impossibile salvare il voto in locale: {e}")

    background.add_task(forward_to_sheet, payload)

    return {"ok": True}


# ---------------------------------------------------------------------------
# File statici: video + frontend buildato
# ---------------------------------------------------------------------------

app.mount("/videos", StaticFiles(directory=VIDEOS_DIR), name="videos")

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIST / "index.html")
