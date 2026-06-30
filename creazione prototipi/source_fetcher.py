from loader import load_source_texts


def get_source_text(concept_id: str):
    source_texts = load_source_texts()

    if concept_id not in source_texts:
        raise KeyError(f"Nessun testo sorgente trovato per: {concept_id}")

    return source_texts[concept_id]