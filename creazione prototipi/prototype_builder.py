from extractor import extract_candidate_properties, extract_typical_properties
from source_fetcher import get_source_text


def build_prototype(concept: dict, rigid_properties: dict) -> dict:
    concept_id = concept["id"]
    concept_type = concept["type"]

    source_payload = get_source_text(concept_id)
    source_text = source_payload["text"]

    #candidate_properties = extract_candidate_properties(source_text)
    typical_properties = extract_typical_properties(source_text, top_k=8)

    rigid = rigid_properties.get(
        concept_id,
        {"positive": [], "negative": []}
    )

    prototype = {
        "id": concept_id,
        "type": concept_type,
        #"source_text": source_text,
        #"candidate_properties": candidate_properties,
        "typical_properties": typical_properties,
        "rigid_properties": {
            "positive": rigid["positive"],
            "negative": rigid["negative"]
        }
    }

    return prototype