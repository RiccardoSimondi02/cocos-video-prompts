# Builds a COCOS input file directly from a JSON file containing prototypes

import sys
import os
import json
import cocos_config as cfg


def load_prototypes(json_path):
    """
    Read prototypes from a JSON file.
    Expected format: list of objects with fields:
      - id
      - type
      - typical_properties
      - rigid_properties { positive: [], negative: [] }
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Prototype file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("The prototype JSON must contain a list of prototypes.")

    return data


def index_prototypes(prototypes):
    """
    Build a dict: prototype_id -> prototype_data
    """
    proto_map = {}

    for proto in prototypes:
        proto_id = proto.get("id")
        if not proto_id:
            raise ValueError("Each prototype must have an 'id' field.")

        if proto_id in proto_map:
            raise ValueError(f"Duplicate prototype id found: {proto_id}")

        proto_map[proto_id] = proto

    return proto_map


def normalize_score(value):
    """
    Clamp probabilities into the usual CoCoS range [0.6, 0.9].
    """
    return round(max(0.6, min(0.9, float(value))), 3)


def get_typical_properties(proto):
    """
    Return dict of typical properties from a prototype.
    """
    return proto.get("typical_properties", {}) or {}


def get_rigid_properties(proto):
    """
    Return list of rigid properties from a prototype.
    Positive props stay as they are.
    Negative props are prefixed with '-'.
    """
    rigid = proto.get("rigid_properties", {}) or {}
    positive = rigid.get("positive", []) or []
    negative = rigid.get("negative", []) or []

    props = []

    for p in positive:
        props.append(str(p).strip())

    for p in negative:
        p = str(p).strip()
        props.append(p if p.startswith("-") else f"-{p}")

    return props


def write_cocos_file(head_proto, modifier_proto):
    """
    Write the final combined input file used by CoCoS.
    """
    os.makedirs(cfg.COCOS_DIR, exist_ok=True)

    head = head_proto["id"]
    modifier = modifier_proto["id"]

    out_path = f"{cfg.COCOS_DIR}/{head}_{modifier}.txt"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Title: {head}-{modifier}\n\n")
        f.write(f"Head Concept Name: {head}\n")
        f.write(f"Modifier Concept Name: {modifier}\n\n")

        # rigid properties
        for p in get_rigid_properties(head_proto):
            f.write(f"head, {p}\n")
        f.write("\n")

        for p in get_rigid_properties(modifier_proto):
            f.write(f"modifier, {p}\n")
        f.write("\n")

        # typical properties
        modifier_typ = get_typical_properties(modifier_proto)
        for p, value in sorted(modifier_typ.items(), key=lambda x: (-x[1], x[0])):
            f.write(f"T(modifier), {p}, {normalize_score(value)}\n")
        f.write("\n")

        head_typ = get_typical_properties(head_proto)
        for p, value in sorted(head_typ.items(), key=lambda x: (-x[1], x[0])):
            f.write(f"T(head), {p}, {normalize_score(value)}\n")
        f.write("\n")

    print(f"Created: {out_path}")


def is_valid_combination(head_proto, modifier_proto):
    """
    Optional constraint for your project:
    - head must be a subject
    - modifier must be a background
    """
    return (
        head_proto.get("type") == "subject"
        and modifier_proto.get("type") == "background"
    )


if __name__ == '__main__':
    prototypes_path = getattr(cfg, "PROTOTYPES_JSON", "prototypes.json")
    prototypes = load_prototypes(prototypes_path)
    proto_map = index_prototypes(prototypes)

    head = ""
    modifier = ""

    # run a specific combination
    if len(sys.argv) == 3:
        head = sys.argv[1]
        modifier = sys.argv[2]

        if head not in proto_map:
            raise ValueError(f"Head concept '{head}' not found in {prototypes_path}")
        if modifier not in proto_map:
            raise ValueError(f"Modifier concept '{modifier}' not found in {prototypes_path}")

        head_proto = proto_map[head]
        modifier_proto = proto_map[modifier]

        if not is_valid_combination(head_proto, modifier_proto):
            raise ValueError(
                f"Invalid combination: head='{head}' must be type 'subject' "
                f"and modifier='{modifier}' must be type 'background'"
            )

        write_cocos_file(head_proto, modifier_proto)

    # run all valid subject-background combinations
    else:
        print("Running all valid subject-background combinations...")
        print("To run a specific combination: python3 cocos_preprocessing.py <head_concept> <modifier_concept>\n")

        for head_proto in prototypes:
            for modifier_proto in prototypes:
                if head_proto["id"] != modifier_proto["id"] and is_valid_combination(head_proto, modifier_proto):
                    write_cocos_file(head_proto, modifier_proto)