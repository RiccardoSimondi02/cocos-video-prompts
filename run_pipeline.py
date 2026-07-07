#!/usr/bin/env python3
"""
run_pipeline.py — esegue in un solo comando l'intera trafila:

    cocos_preprocessing.py  ->  cocos.py  ->  prompt_gen.py

Uso:
    python3 run_pipeline.py <subject> <background>

Esempio:
    python3 run_pipeline.py wrestler Turin
    python3 run_pipeline.py astronaut tropical_beach --rebuild-prototypes

Opzioni:
    --rebuild-prototypes   Rigenera prima TUTTI i prototipi da zero
                            (equivale a lanciare "creazione prototipi/mainv3.py").
                            Da usare solo se hai aggiunto/modificato concetti
                            in data/concepts.json o data/source_texts.json.

Il risultato finale (final_prompt incluso) viene:
    - scritto in generazione_prompt/prompt.json (come prima, sovrascritto)
    - salvato anche in generazione_prompt/results/<subject>_<background>.json
      (così le esecuzioni precedenti non vengono perse)
"""

import argparse
import json
import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
PROTO_DIR = ROOT / "creazione prototipi"
COMBINATORE_DIR = ROOT / "combinatore"
PROMPT_DIR = ROOT / "generazione_prompt"
RESULTS_DIR = PROMPT_DIR / "results"


def run_step(title, cmd, cwd):
    """Esegue un comando, mostra il suo output e ritorna stdout+stderr come stringa."""
    print(f"\n=== {title} ===")
    print(f"$ {' '.join(cmd)}   (in {cwd})")

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"\n[ERRORE] '{title}' ha fallito (exit code {result.returncode}). Pipeline interrotta.")
        sys.exit(result.returncode)

    return result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description="Esegue l'intera pipeline subject+background -> prompt video.")
    parser.add_argument("subject", help="id del concetto subject (es. wrestler, astronaut)")
    parser.add_argument("background", help="id del concetto background (es. Turin, tropical_beach)")
    parser.add_argument(
        "--rebuild-prototypes",
        action="store_true",
        help="Rigenera tutti i prototipi (mainv3.py) prima di combinare.",
    )
    args = parser.parse_args()

    subject = args.subject
    background = args.background
    python = sys.executable  # usa lo stesso interprete/venv con cui lanci questo script

    # Step 0 (opzionale): rigenerazione di TUTTI i prototipi
    if args.rebuild_prototypes:
        run_step(
            "Rigenerazione prototipi (mainv3.py)",
            [python, "mainv3.py"],
            cwd=PROTO_DIR,
        )

    # Step 1: preprocessing -> crea combinatore/combined/<subject>_<background>.txt
    run_step(
        "Preprocessing CoCoS",
        [python, "cocos_preprocessing.py", subject, background],
        cwd=COMBINATORE_DIR,
    )

    combined_filename = f"{subject}_{background}.txt"
    combined_path = COMBINATORE_DIR / "combined" / combined_filename

    if not combined_path.exists():
        print(f"\n[ERRORE] File combinato non trovato: {combined_path}")
        sys.exit(1)

    # Step 2: combinazione vera e propria con CoCoS
    cocos_output = run_step(
        "Combinazione concetti (cocos.py)",
        [python, "cocos.py", f"combined/{combined_filename}"],
        cwd=COMBINATORE_DIR,
    )

    if "NO recommended scenarios" in cocos_output:
        print(
            "\n[ERRORE] CoCoS non ha trovato nessuno scenario consistente per "
            f"'{subject}' + '{background}'. Pipeline interrotta: non ha senso "
            "generare il prompt senza uno scenario valido."
        )
        sys.exit(1)

    # Step 3: verbalizzazione con LLM -> generazione_prompt/prompt.json
    run_step(
        "Generazione prompt (prompt_gen.py)",
        [python, "prompt_gen.py", combined_filename],
        cwd=PROMPT_DIR,
    )

    # Salvataggio di una copia permanente, per non perdere i risultati delle coppie precedenti
    prompt_json_path = PROMPT_DIR / "prompt.json"
    if prompt_json_path.exists():
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        result_copy_path = RESULTS_DIR / f"{subject}_{background}.json"
        result_copy_path.write_text(
            prompt_json_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

        with open(prompt_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print("\n=== RISULTATO FINALE ===")
        print(data.get("final_prompt", "(final_prompt non trovato nel JSON)"))
        print(f"\nSalvato anche in: {result_copy_path}")
    else:
        print("\n[ATTENZIONE] prompt.json non trovato dopo l'esecuzione di prompt_gen.py.")
        sys.exit(1)


if __name__ == "__main__":
    main()
