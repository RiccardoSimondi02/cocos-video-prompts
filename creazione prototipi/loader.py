import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def load_json(filename: str) -> Any:
    path = DATA_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_concepts() -> list[dict]:
    data = load_json("concepts.json")

    if not isinstance(data, list):
        raise ValueError("concepts.json deve contenere una lista di concetti")

    for concept in data:
        if not isinstance(concept, dict):
            raise ValueError("Ogni concetto deve essere un oggetto JSON")

        required_fields = {"id", "type", "query"}
        if not required_fields.issubset(concept.keys()):
            raise ValueError("Ogni concetto deve avere i campi: id, type, query")

        if concept["type"] not in {"subject", "background"}:
            raise ValueError(
                f"Tipo non valido per {concept['id']}: {concept['type']}"
            )

    return data


def load_rigid_properties() -> dict:
    data = load_json("rigid_properties.json")

    if not isinstance(data, dict):
        raise ValueError("rigid_properties.json deve contenere un oggetto/dizionario")

    for concept_id, props in data.items():
        if not isinstance(props, dict):
            raise ValueError(
                f"Le proprietà rigide di {concept_id} devono essere un oggetto"
            )

        required_fields = {"positive", "negative"}
        if not required_fields.issubset(props.keys()):
            raise ValueError(
                f"{concept_id} deve avere i campi 'positive' e 'negative'"
            )

        if not isinstance(props["positive"], list):
            raise ValueError(
                f"Il campo 'positive' di {concept_id} deve essere una lista"
            )

        if not isinstance(props["negative"], list):
            raise ValueError(
                f"Il campo 'negative' di {concept_id} deve essere una lista"
            )

    return data


def load_source_texts() -> dict:
    data = load_json("source_texts.json")

    if not isinstance(data, dict):
        raise ValueError("source_texts.json deve contenere un oggetto/dizionario")

    for concept_id, payload in data.items():
        if not isinstance(payload, dict):
            raise ValueError(f"La sorgente di {concept_id} deve essere un oggetto")

        required_fields = {"text"}
        if not required_fields.issubset(payload.keys()):
            raise ValueError(
                f"La sorgente di {concept_id} deve avere i campi: text"
            )

        if not isinstance(payload["text"], str):
            raise ValueError(f"Il campo 'text' di {concept_id} deve essere una stringa")

    return data