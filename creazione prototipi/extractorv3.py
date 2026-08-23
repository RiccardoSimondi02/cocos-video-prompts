import re
from collections import Counter, defaultdict
from math import log
from typing import Any

import spacy

nlp = spacy.load("en_core_web_sm")


# Config

ALLOWED_UNIGRAM_POS = {"NOUN", "ADJ", "PROPN"}

ALLOWED_BIGRAM_PATTERNS = {
    ("ADJ", "NOUN"),
    ("NOUN", "NOUN"),
    ("ADJ", "PROPN"),
    ("PROPN", "NOUN"),
}

# Utils per i bigrammi
ABSTRACT_HEADS = {
    "scheme", "proportion",
    "world", "system", "process", "structure", "condition", "color"
}

GENERIC_LEMMAS = {
    "thing", "element", "object", "person", "figure",
    "type", "kind", "way", "part", "area", "place",
    "someone", "something", "life", "training", "body",
    "visual", "scene", "long", "silhouette", "like",
    "concept", "property", "feature", "image", "video", "large", 
    "small", "formation", "face", "design", "visible", "thick"
}


# es. non-human -> non_human
IMPORTANT_HYPHEN_PREFIXES = {
    "non", "anti", "pre", "post", "semi", "multi",
    "ultra", "hyper", "high", "low"
}




# Normalization

def normalize_text(text: str) -> str:
    """
    Normalizza il testo senza distruggere i composti con trattino.

    Esempi:
    - non-human -> non_human
    - high-tech -> high_tech
    - neon-lit -> neon_lit
    """
    text = text.lower()

    # convert words with -
    # es. non-human -> non_human
    text = re.sub(r"\b([a-z]+)-([a-z]+)\b", r"\1_\2", text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_valid_term_string(term: str) -> bool:
    """
    Accetta:
    - parole alfabetiche: helmet
    - composti con underscore: non_human, high_tech
    """
    return bool(re.fullmatch(r"[a-z]+(?:_[a-z]+)*", term))


def clean_lemma(token) -> str:
    """
    Restituisce il lemma pulito.

    Nota:
    se il token contiene underscore, spaCy può restituire lemma strani.
    In quel caso usiamo direttamente token.text.
    """
    text = token.text.strip().lower()

    if "_" in text:
        return text

    return token.lemma_.strip().lower()



def extract_hyphenated_terms(raw_text: str) -> list[str]:
    """
    Estrae parole composte originarie con trattino.

    Esempi:
    - non-human -> non_human
    - high-tech -> high_tech
    - neon-lit -> neon_lit

    Serve perché alcuni composti hanno significato diverso
    dalla semplice somma dei token separati.
    """
    raw_text = raw_text.lower()

    matches = re.findall(r"\b[a-z]+-[a-z]+\b", raw_text)

    terms = []

    for match in matches:
        left, right = match.split("-", 1)

        term = f"{left}_{right}"

        if not is_valid_term_string(term):
            continue

        if left in GENERIC_LEMMAS and right in GENERIC_LEMMAS:
            continue

        if len(right) < 3:
            continue

        terms.append(term)

    return terms


# Token filter

def is_good_unigram_token(token) -> bool:
    """
    Decide se un token spaCy può essere usato come unigramma.
    """
    lemma = clean_lemma(token)

    if not is_valid_term_string(lemma):
        return False

    if token.is_stop:
        return False

    if token.pos_ not in ALLOWED_UNIGRAM_POS:
        return False

    if len(lemma) < 3:
        return False

    if lemma in GENERIC_LEMMAS:
        return False

    return True


def is_good_bigram_part(token) -> bool:
    """
    Versione leggermente più rigida per i token che entrano nei bigrammi.
    Evita di creare bigrammi strani con termini già composti.
    """
    lemma = clean_lemma(token)

    if "_" in lemma:
        return False

    return is_good_unigram_token(token)


# Term extraction

def extract_unigrams(doc) -> list[str]:
    """
    Estrae lemmi singoli utili.
    """
    lemmas = []

    for token in doc:
        if not is_good_unigram_token(token):
            continue

        lemmas.append(clean_lemma(token))

    return lemmas


def extract_surface_bigrams(doc) -> list[str]:
    """
    Estrae bigrammi da token realmente consecutivi nel testo.

    Esempi:
    - white suit -> white_suit
    - space helmet -> space_helmet
    - historic center -> historic_center
    """
    bigrams = []

    for i in range(len(doc) - 1):
        a = doc[i]
        b = doc[i + 1]

        if not is_good_bigram_part(a):
            continue

        if not is_good_bigram_part(b):
            continue

        if (a.pos_, b.pos_) not in ALLOWED_BIGRAM_PATTERNS:
            continue

        lemma_a = clean_lemma(a)
        lemma_b = clean_lemma(b)

        if lemma_a == lemma_b:
            continue

        bigrams.append(f"{lemma_a}_{lemma_b}")

    return bigrams


def extract_chunk_bigrams(doc) -> list[str]:
    """
    Estrae bigrammi dai noun chunks.

    Utile per recuperare coppie nominali significative anche quando
    compaiono dentro gruppi nominali più lunghi.
    """
    bigrams = []

    for chunk in doc.noun_chunks:
        valid_tokens = [
            token for token in chunk
            if is_good_bigram_part(token)
        ]

        if len(valid_tokens) < 2:
            continue

        for i in range(len(valid_tokens) - 1):
            a = valid_tokens[i]
            b = valid_tokens[i + 1]

            if (a.pos_, b.pos_) not in ALLOWED_BIGRAM_PATTERNS:
                continue

            lemma_a = clean_lemma(a)
            lemma_b = clean_lemma(b)

            if lemma_a == lemma_b:
                continue

            bigrams.append(f"{lemma_a}_{lemma_b}")

    return bigrams


def extract_terms(text: str) -> list[str]:
    """
    Estrae una lista combinata di:
    - unigrammi
    - bigrammi da superficie
    - bigrammi da noun chunks
    - composti originari con trattino

    I termini composti vengono mantenuti con underscore:
    - non-human -> non_human
    - white suit -> white_suit
    - space helmet -> space_helmet
    """
    raw_text = text.lower()

    hyphenated_terms = extract_hyphenated_terms(raw_text)

    normalized_text = normalize_text(text)
    doc = nlp(normalized_text)

    unigrams = extract_unigrams(doc)
    surface_bigrams = extract_surface_bigrams(doc)
    chunk_bigrams = extract_chunk_bigrams(doc)

    all_terms = []
    all_terms.extend(unigrams)
    all_terms.extend(surface_bigrams)
    all_terms.extend(chunk_bigrams)
    all_terms.extend(hyphenated_terms)
    
    all_terms = [
        t for t in all_terms
        if not any(part in ABSTRACT_HEADS for part in t.split("_"))
    ]

    return all_terms


# Normalization score

def normalize_dict_scores(
    raw_scores: dict[str, float],
    out_min: float = 0.60,
    out_max: float = 0.90
) -> dict[str, float]:
    """
    Normalizza un dizionario di score nel range [out_min, out_max].
    """
    if not raw_scores:
        return {}

    values = list(raw_scores.values())
    min_score = min(values)
    max_score = max(values)

    if min_score == max_score:
        mid = round((out_min + out_max) / 2, 2)
        return {term: mid for term in raw_scores}

    normalized = {}

    for term, score in raw_scores.items():
        scaled = out_min + (
            (score - min_score) / (max_score - min_score)
        ) * (out_max - out_min)

        normalized[term] = round(
            max(out_min, min(out_max, scaled)),
            2
        )

    return normalized


def _minmax_01(scores: dict[str, float]) -> dict[str, float]:
    """
    Normalizza valori in [0, 1].
    """
    if not scores:
        return {}

    values = list(scores.values())
    min_v = min(values)
    max_v = max(values)

    if min_v == max_v:
        return {k: 1.0 for k in scores}

    return {
        k: (v - min_v) / (max_v - min_v)
        for k, v in scores.items()
    }


# TF-IDF hybrid

def compute_document_frequency(
    processed_docs: list[list[str]]
) -> dict[str, int]:
    """
    DF = numero di documenti in cui compare ciascun termine.

    Il termine può essere:
    - unigramma: helmet
    - bigramma: space_helmet
    - composto con trattino normalizzato: non_human
    """
    df = defaultdict(int)

    for doc_terms in processed_docs:
        for term in set(doc_terms):
            df[term] += 1

    return dict(df)


def score_terms_hybrid_for_document(
    doc_terms: list[str],
    doc_freq: Counter,
    df: dict[str, int],
    n_docs: int,
    alpha_tfidf: float = 0.60,
    beta_freq: float = 0.40,
) -> dict[str, float]:
    """
    Score ibrido basato su:
    - TF-IDF normalizzato
    - frequenza locale normalizzata
    """
    if not doc_terms:
        return {}

    total_terms = len(doc_terms)

    tfidf_scores = {}

    for term, freq in doc_freq.items():
        tf = freq / total_terms
        idf = log((1 + n_docs) / (1 + df.get(term, 0))) + 1
        tfidf_scores[term] = tf * idf

    tfidf_norm = _minmax_01(tfidf_scores)
    freq_norm = _minmax_01(dict(doc_freq))

    hybrid = {}

    for term in doc_freq:
        score = (
            alpha_tfidf * tfidf_norm.get(term, 0.0)
            + beta_freq * freq_norm.get(term, 0.0)
        )

        hybrid[term] = max(score, 0.0)

    return hybrid


# Delete self-term

def get_concept_self_terms(concept_id: str) -> set[str]:
    """
    Elimina come possibili properties il nome del concetto stesso.

    Esempi:
    - astronaut -> astronaut
    - tropical_beach -> tropical, beach
    - snowy_forest -> snowy, forest
    - non_human_creature -> non, human, creature
    """
    concept_id = concept_id.lower().strip()
    parts = re.split(r"[_\-\s]+", concept_id)

    return {
        p for p in parts
        if p and p not in GENERIC_LEMMAS
    }


def is_self_bigram(term: str, self_terms: set[str]) -> bool:
    """
    Scarta termini composti formati esattamente dai self terms.

    Esempio per tropical_beach:
    - tropical_beach -> da scartare
    """
    if "_" not in term:
        return False

    parts = term.split("_")

    return all(part in self_terms for part in parts)


def filter_self_terms(
    terms: list[str],
    concept_id: str
) -> list[str]:
    """
    Rimuove:
    - il nome del concetto stesso;
    - composti formati solo dai pezzi del nome del concetto.
    """
    self_terms = get_concept_self_terms(concept_id)

    filtered_terms = []

    for term in terms:
        if term in self_terms:
            continue

        if is_self_bigram(term, self_terms):
            continue

        filtered_terms.append(term)

    return filtered_terms


# Decide between uni and bigrams contaning the same noun

def prune_unigrams_covered_by_bigrams(
    ranked_terms: list[tuple[str, float]],
    margin: float = 0.05
) -> list[tuple[str, float]]:
    """
    Se un bigramma ha score entro 'margin' rispetto a uno dei suoi unigrammi,
    il bigramma viene preferito e l'unigramma viene rimosso.

    Esempio con margin=0.05:
    - bigramma 0.60, unigramma 0.63 -> rimuovi unigramma
    - bigramma 0.60, unigramma 0.70 -> tieni entrambi
    """
    if not ranked_terms:
        return []

    score_map = dict(ranked_terms)
    unigrams_to_remove = set()

    for term, term_score in ranked_terms:
        if "_" not in term:
            continue

        parts = term.split("_")

        if len(parts) < 2:
            continue

        for unigram in parts:
            unigram_score = score_map.get(unigram)

            if unigram_score is None:
                continue

            if unigram_score - term_score <= margin:
                unigrams_to_remove.add(unigram)

    pruned = []

    for term, score in ranked_terms:
        if term in unigrams_to_remove and "_" not in term:
            continue

        pruned.append((term, score))

    return pruned


def rerank_after_bigram_pruning(
    raw_scores: dict[str, float],
    top_k: int,
    margin: float = 0.05
) -> dict[str, float]:
    """
    Ordina i termini per score, applica la pruning rule
    unigramma/bigramma, ritaglia a top_k e normalizza.
    """
    ranked = sorted(
        raw_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    pruned_ranked = prune_unigrams_covered_by_bigrams(
        ranked_terms=ranked,
        margin=margin
    )

    final_ranked = pruned_ranked[:top_k]

    return normalize_dict_scores(dict(final_ranked))


# Main func

def extract_typical_properties_from_corpus(
    concepts: list[dict[str, Any]],
    top_k: int = 8
) -> list[dict[str, Any]]:
    """
    Estrae proprietà tipiche da un corpus di concetti.

    Input atteso:
    [
      {
        "id": "astronaut",
        "type": "subject",
        "text": "..."
      },
      {
        "id": "tropical_beach",
        "type": "background",
        "text": "..."
      }
    ]

    Output:
    [
      {
        "id": "astronaut",
        "type": "subject",
        "typical_properties": {
            "space_suit": 0.90,
            "helmet": 0.82,
            ...
        }
      }
    ]
    """
    if not concepts:
        return []

    processed_docs_terms = []
    valid_concepts = []

    for concept in concepts:
        concept_id = concept.get("id")
        concept_type = concept.get("type")
        text = concept.get("text", "")

        if not concept_id:
            raise ValueError("Ogni concetto deve avere un campo 'id'.")

        if not concept_type:
            raise ValueError(
                f"Il concetto '{concept_id}' non ha il campo 'type'."
            )

        doc_terms = extract_terms(text)

        processed_docs_terms.append(doc_terms)
        valid_concepts.append(concept)

    df = compute_document_frequency(processed_docs_terms)
    n_docs = len(processed_docs_terms)

    prototypes = []

    for idx, concept in enumerate(valid_concepts):
        concept_id = concept["id"]
        concept_type = concept["type"]

        doc_terms = processed_docs_terms[idx]

        filtered_doc_terms = filter_self_terms(
            terms=doc_terms,
            concept_id=concept_id
        )

        freq = Counter(filtered_doc_terms)

        raw_scores = score_terms_hybrid_for_document(
            doc_terms=filtered_doc_terms,
            doc_freq=freq,
            df=df,
            n_docs=n_docs,
        )

        normalized = rerank_after_bigram_pruning(
            raw_scores=raw_scores,
            top_k=top_k,
            margin=0.05
        )

        prototypes.append({
            "id": concept_id,
            "type": concept_type,
            "typical_properties": normalized
        })

    return prototypes


