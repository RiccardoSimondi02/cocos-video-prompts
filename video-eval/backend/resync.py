"""
Reinvia al Google Sheet i voti rimasti in `votes_unsynced.jsonl`.

Ogni voto era già stato salvato in modo durevole in `votes.jsonl`; qui proviamo
soltanto a recapitare al Sheet quelli il cui inoltro in background era fallito.
I voti recapitati con successo vengono rimossi dal file; quelli che falliscono
di nuovo restano, così puoi rilanciare lo script più tardi.

Uso:
    cd video-eval/backend
    python3 resync.py            # reinvia i voti non sincronizzati
    python3 resync.py --dry-run  # mostra soltanto quanti ne verrebbero reinviati
"""

import json
import sys

from main import VOTES_UNSYNCED_FILE, send_to_sheet


def load_pending():
    if not VOTES_UNSYNCED_FILE.exists():
        return []
    pending = []
    for line in VOTES_UNSYNCED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            pending.append(json.loads(line))
    return pending


def rewrite_pending(remaining):
    """Riscrive il file con i soli voti ancora da sincronizzare (in modo atomico)."""
    if not remaining:
        VOTES_UNSYNCED_FILE.unlink(missing_ok=True)
        return
    tmp = VOTES_UNSYNCED_FILE.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for payload in remaining:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    tmp.replace(VOTES_UNSYNCED_FILE)


def main():
    dry_run = "--dry-run" in sys.argv

    pending = load_pending()
    if not pending:
        print("Nessun voto da reinviare: tutto sincronizzato.")
        return

    print(f"Voti da reinviare: {len(pending)}")
    if dry_run:
        return

    remaining = []
    sent = 0
    for i, payload in enumerate(pending, 1):
        try:
            send_to_sheet(payload)
            sent += 1
            print(f"  [{i}/{len(pending)}] OK  ({payload.get('concept', '?')})")
        except Exception as e:  # noqa: BLE001
            remaining.append(payload)
            print(f"  [{i}/{len(pending)}] FALLITO: {e}")

    rewrite_pending(remaining)
    print(f"\nReinviati: {sent}. Ancora in coda: {len(remaining)}.")
    if remaining:
        print(f"Rilancia lo script più tardi per riprovare ({VOTES_UNSYNCED_FILE.name}).")


if __name__ == "__main__":
    main()
