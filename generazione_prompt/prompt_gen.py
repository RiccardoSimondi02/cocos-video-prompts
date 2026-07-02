import json
import re
from pathlib import Path
from typing import Any
import os
from dotenv import load_dotenv
from google import genai
import sys

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY non trovata nel file .env")

client = genai.Client(api_key=api_key)


# Parse CoCoS output

def parse_cocos_output(text: str) -> dict[str, Any]:
    head_name = None
    modifier_name = None

    head_candidates: dict[str, float] = {}
    modifier_candidates: dict[str, float] = {}

    head_match = re.search(r"Head Concept Name:\s*(.+)", text)
    mod_match = re.search(r"Modifier Concept Name:\s*(.+)", text)

    if head_match:
        head_name = head_match.group(1).strip()
    if mod_match:
        modifier_name = mod_match.group(1).strip()

    if not head_name or not modifier_name:
        raise ValueError("Could not extract head/modifier names from CoCoS output.")

    prop_pattern = re.compile(
        r"^T\((head|modifier)\),\s*([A-Za-z0-9_\-]+),\s*([0-9]*\.?[0-9]+)\s*$",
        re.MULTILINE,
    )

    for role, prop, score in prop_pattern.findall(text):
        if role == "head":
            head_candidates[prop] = float(score)
        else:
            modifier_candidates[prop] = float(score)

    rigid_pattern = re.compile(
        r"^(head|modifier),\s*(-?[A-Za-z0-9_\-]+)\s*$",
        re.MULTILINE,
    )

    negative_props = []
    for role, prop in rigid_pattern.findall(text):
        if prop.startswith("-"):
            negative_props.append({"property": prop[1:], "score": 1.0})

    result_match = re.search(r"Result:\s*(\{.*?\})", text, re.DOTALL)
    if not result_match:
        raise ValueError("Could not find Result JSON in CoCoS output.")

    result_raw = result_match.group(1).strip()

    try:
        result_data = json.loads(result_raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Result JSON: {exc}") from exc

    scenario_probability = result_data.pop("@scenario_probability", None)
    subject_properties: list[dict[str, Any]] = []
    environment_properties: list[dict[str, Any]] = []
    unknown_properties: list[dict[str, Any]] = []

    for prop, score in result_data.items():
        item = {"property": prop, "score": float(score)}

        if prop in head_candidates:
            subject_properties.append(item)
        elif prop in modifier_candidates:
            environment_properties.append(item)
        else:
            unknown_properties.append(item)

    subject_properties.sort(key=lambda x: x["score"], reverse=True)
    environment_properties.sort(key=lambda x: x["score"], reverse=True)
    unknown_properties.sort(key=lambda x: x["score"], reverse=True)

    return {
        "subject": head_name,
        "environment": modifier_name,
        "subject_properties": subject_properties,
        "environment_properties": environment_properties,
        "negative_properties": negative_props,
        "unknown_properties": unknown_properties,
    }


def parse_cocos_file(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    return parse_cocos_output(text)


# Build LLM payload

def deduplicate_properties(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_name: dict[str, dict[str, Any]] = {}

    for item in properties:
        prop = item["property"]
        score = float(item["score"])

        if prop not in best_by_name or score > float(best_by_name[prop]["score"]):
            best_by_name[prop] = {"property": prop, "score": score}

    return sorted(best_by_name.values(), key=lambda x: x["score"], reverse=True)


def select_top_k(properties: list[dict[str, Any]], top_k: int | None = None) -> list[dict[str, Any]]:
    if top_k is None:
        return properties
    return properties[:top_k]


def build_llm_payload(
    parsed_data: dict[str, Any],
    subject_top_k: int | None = 6,
    environment_top_k: int | None = 6,
) -> dict[str, Any]:
    subject_properties = deduplicate_properties(parsed_data.get("subject_properties", []))
    environment_properties = deduplicate_properties(parsed_data.get("environment_properties", []))
    negative_properties = deduplicate_properties(parsed_data.get("negative_properties", []))
    unknown_properties = deduplicate_properties(parsed_data.get("unknown_properties", []))

    subject_properties = select_top_k(subject_properties, subject_top_k)
    environment_properties = select_top_k(environment_properties, environment_top_k)

    return {
        "subject": parsed_data["subject"],
        "subject_properties": [item["property"] for item in subject_properties],
        "environment": parsed_data["environment"],
        "environment_properties": [item["property"] for item in environment_properties],
        "negative_properties": [item["property"] for item in negative_properties],
        "unknown_properties": [item["property"] for item in unknown_properties],
        "constraints": {
            "do_not_add_new_content": True,
            "preserve_subject_environment_distinction": True,
            "output_type": "single video prompt",
            "style": "natural, concise, visually descriptive",
        },
    }


# Generate prompt with LLM

def generate_prompt_with_llm(
    payload: dict[str, Any],
    model: str = "gemini-2.5-flash",
) -> str:
    full_prompt = f"""
You are a controlled prompt verbalizer.

Convert the structured input into exactly one natural video-generation prompt.

Rules:
- Use only the provided subject, environment, and properties.
- Do not add new semantic content.
- Do not introduce new objects, characters, actions, locations, weather, lighting,
  camera instructions, or style elements unless directly supported by the input.
- Preserve the distinction between subject and environment.
- Output exactly one concise, visually descriptive sentence.
- Highlight the negative properties.

Structured input:
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=genai.types.GenerateContentConfig(  
            temperature=0.0,                            # temperature = 0 so output is replicable
        ),
    )

    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Empty response from Gemini model.")

    return text.strip()


# End-to-end pipeline, build all toghether

def generate_prompt_from_cocos_file(
    file_path: str,
    model: str = "gemini-2.5-flash",
    subject_top_k: int | None = 6,
    environment_top_k: int | None = 6,
) -> dict[str, Any]:
    parsed = parse_cocos_file(file_path)

    payload = build_llm_payload(
        parsed_data=parsed,
        subject_top_k=subject_top_k,
        environment_top_k=environment_top_k,
    )

    final_prompt = generate_prompt_with_llm(
        payload=payload,
        model=model,
    )
    
    return {
        "payload": payload,
        "final_prompt": final_prompt,
    }

# Saving all in a JSON file

def save_result(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


if __name__ == "__main__":

    filename = sys.argv[1]
    file_path = Path("../combinatore/combined") / filename

    result = generate_prompt_from_cocos_file(
        file_path=str(file_path),
        model="gemini-2.5-flash",
        subject_top_k=8,
        environment_top_k=8,
    )

    save_result(result, "prompt.json")