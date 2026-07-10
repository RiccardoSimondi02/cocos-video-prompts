"""
Backend per la valutazione di coppie di video.

Ogni coppia = un video "mine" (generato col prompt della tesi) e un video "base".
L'utente vede solo "Video A" / "Video B", in ordine casuale, e non sa quale sia
quale. Il backend calcola a quale sistema corrisponde ogni scelta e inoltra il
voto a un Google Sheet (via Google Apps Script).
"""

import json
import os
import random
import uuid
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / "videos"
PAIRS_FILE = BASE_DIR / "pairs.json"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL", "").strip()

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


def send_to_sheet(payload: dict):
    """Inoltra un voto al Google Sheet. Solleva eccezione se fallisce."""
    if not SHEET_WEBHOOK_URL:
        raise RuntimeError("SHEET_WEBHOOK_URL non configurato")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SHEET_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    result = json.loads(body)
    if not result.get("ok"):
        raise RuntimeError(f"Sheet ha risposto con errore: {result}")


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

        items.append({
            "concept": p["concept"],
            "label": p["label"],
            "video_A": f"/videos/{video_A}",
            "video_B": f"/videos/{video_B}",
            "system_A": system_A,
            "system_B": system_B,
        })

    return {"session_id": session_id, "items": items}


@app.post("/api/vote")
def submit_vote(vote: VoteIn):
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
        send_to_sheet(payload)
    except Exception as e:
        # Non perdere il voto silenziosamente: segnala l'errore al client.
        raise HTTPException(502, f"Impossibile salvare il voto: {e}")

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
