from loader import load_concepts, load_rigid_properties
from source_fetcher import get_source_text
from extractorv3 import extract_typical_properties_from_corpus
from exporter import save_json


def main():
    concepts = load_concepts()
    rigid_properties = load_rigid_properties()

    concepts_for_extraction = []

    for concept in concepts:
        concept_id = concept["id"]
        concept_type = concept["type"]

        source_payload = get_source_text(concept_id)
        text = source_payload["text"]

        concepts_for_extraction.append({
            "id": concept_id,
            "type": concept_type,
            "text": text
        })

    extracted = extract_typical_properties_from_corpus(
        concepts_for_extraction,
        top_k=9
    )

    prototypes = []

    for item in extracted:
        concept_id = item["id"]

        rigid = rigid_properties.get(
            concept_id,
            {"positive": [], "negative": []}
        )

        prototype = {
            "id": concept_id,
            "type": item["type"],
            "typical_properties": item["typical_properties"],
            "rigid_properties": rigid
        }

        prototypes.append(prototype)

    save_json("prototypesv3.json", prototypes)

    print("Creati prototipi:", len(prototypes))
    print("File salvato in: prototypesv3.json")

    for prototype in prototypes:
        print(f"- {prototype['id']}")


if __name__ == "__main__":
    main()