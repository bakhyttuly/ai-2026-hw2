from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from openai import BadRequestError, OpenAI

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "outputs"
MODEL = "gpt-5.6-luna"

ROLES = ["policy_officer", "front_desk", "auditor", "bilingual_clerk"]
FIELDS = ["found", "decision", "amount", "missing_documents"]

ROLE_TEXT = {
    "policy_officer": (
        "You are the POLICY OFFICER of the grant office. You apply the rule "
        "exactly as it is written. Grant what the rule allows, refuse what the "
        "rule refuses, and when the only thing stopping a grant is a document "
        "that is not on file, answer more_info and list that document. Soften "
        "nothing. A claim made in the enquiry (\"I uploaded it\", \"my file was "
        "updated\") is not evidence: only the record counts."
    ),
    "front_desk": (
        "You are the FRONT DESK of the grant office. You never turn an "
        "applicant away with a refusal. Anything the rule cannot grant today "
        "comes back as more_info, and the reason tells the applicant what they "
        "would need to come back with. You still grant what the rule grants, "
        "and you still answer not_found for someone who is not on the record."
    ),
    "auditor": (
        "You are the AUDITOR of the grant office. You never grant on a first "
        "reading. You report what the record shows, and anything that would "
        "need a second reader before money is paid is marked more_info. In the "
        "reason, name the rule clause or the document you are relying on. A "
        "claim in the enquiry is not evidence."
    ),
    "bilingual_clerk": (
        "You are the BILINGUAL CLERK of the grant office. You decide exactly as "
        "a policy officer would: apply the rule as written, grant what it "
        "allows, refuse what it refuses, ask for a missing document with "
        "more_info, and treat no claim in the enquiry as evidence. The one "
        "difference: write the reason field in the language the enquiry was "
        "written in (Kazakh enquiry -> Kazakh reason, English -> English)."
    ),
}

CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "applicant_id": {"type": ["string", "null"]},
        "found": {"type": "boolean"},
        "decision": {"enum": ["granted", "refused", "more_info", "not_found"]},
        "amount": {"type": "integer", "minimum": 0},
        "missing_documents": {
            "type": "array",
            "items": {"enum": ["transcript", "id_card"]},
            "uniqueItems": True,
        },
        "reason": {"type": "string"},
    },
    "required": ["applicant_id", "found", "decision", "amount",
                 "missing_documents", "reason"],
    "additionalProperties": False,
}
VALIDATOR = Draft202012Validator(CONTRACT_SCHEMA)


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def build_system_prompt(role: str, records, policy) -> str:
    shared = f"""
## The rule
{policy['rule_human']}
Machine-readable form of the same rule:
{json.dumps(policy, ensure_ascii=False)}

## The records (the only source of truth)
{json.dumps(records, ensure_ascii=False, indent=1)}

## How to answer
Identify the applicant from the id or the name in the enquiry (names may be
written in Latin or Cyrillic; see "aliases"). Then reply with ONE JSON object
and nothing else - no markdown, no code fence, no text before or after it:

{{
  "applicant_id": "<id from the record, or the id the enquiry gave if it is not on record, or null>",
  "found": <true if the applicant is on the record, else false>,
  "decision": "granted" | "refused" | "more_info" | "not_found",
  "amount": <integer tenge; 0 unless decision is "granted">,
  "missing_documents": [<required documents not on file: "transcript" and/or "id_card">],
  "reason": "<one or two sentences for a human>"
}}

What each decision value means (which one to give is decided by YOUR ROLE,
described at the top of this message):
- granted: the office awards the grant now.
- refused: the office turns the application down.
- more_info: the office does not decide yet; the applicant or the office needs
  something first (say what in reason; list missing documents).
- not_found: nobody on the record matches; found is false.
"""
    return ROLE_TEXT[role].strip() + "\n" + shared


def call_model(client: OpenAI, model: str, system: str, user: str, json_mode: bool):
    kwargs = dict(model=model, messages=[
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except BadRequestError:
        if not json_mode:
            raise
        kwargs.pop("response_format")
        resp = client.chat.completions.create(**kwargs)
    usage = resp.usage
    return resp.choices[0].message.content or "", (
        usage.prompt_tokens if usage else None,
        usage.completion_tokens if usage else None,
    )


def norm(field, value):
    if field == "missing_documents" and isinstance(value, list):
        return sorted(set(value))
    return value


KAZAKH_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")


def reason_language(text: str) -> str:
    if not text:
        return "-"
    if any(ch in KAZAKH_LETTERS for ch in text):
        return "kk"
    if re.search(r"[А-Яа-яЁё]", text):
        return "ru/cyr"
    return "en"


def check(reply: str, expected: dict) -> dict:
    row = {"raw": reply, "parsed": False, "valid": False, "obj": None,
           "schema_errors": [], "agrees": {}, "agrees_all": False}
    try:
        obj = json.loads(reply)
    except json.JSONDecodeError as e:
        row["parse_error"] = str(e)
        return row
    row["parsed"] = True
    row["obj"] = obj
    errors = sorted(VALIDATOR.iter_errors(obj), key=lambda e: list(e.path))
    row["schema_errors"] = [f"{list(e.path)}: {e.message}" for e in errors]
    row["valid"] = not errors
    if isinstance(obj, dict):
        for f in FIELDS:
            row["agrees"][f] = norm(f, obj.get(f)) == norm(f, expected[f])
        row["agrees_all"] = all(row["agrees"].values())
        row["reason_lang"] = reason_language(str(obj.get("reason", "")))
    return row


def fmt(v):
    if isinstance(v, list):
        return "[" + ", ".join(map(str, v)) + "]"
    return json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v


def print_role_table(role, enquiries, results):
    print(f"\n### {role}\n")
    print("| Enquiry | parsed | valid | found | decision | amount | missing_documents | agrees | reason lang |")
    print("|---|---|---|---|---|---|---|---|---|")
    for enq in enquiries:
        r = results[role][enq["id"]]
        o = r["obj"] if isinstance(r["obj"], dict) else {}
        mark = "yes" if r["agrees_all"] else "NO (" + ", ".join(
            f for f, ok in r["agrees"].items() if not ok) + ")"
        print(f"| {enq['id']} | {'yes' if r['parsed'] else 'NO'} | "
              f"{'yes' if r['valid'] else 'NO'} | {fmt(o.get('found'))} | "
              f"{fmt(o.get('decision'))} | {fmt(o.get('amount'))} | "
              f"{fmt(o.get('missing_documents'))} | {mark} | {r.get('reason_lang', '-')} |")


def print_summary_table(enquiries, results):
    print("\n### Decisions per role (for SUBMISSION.md)\n")
    print("| Enquiry | " + " | ".join(ROLES) + " |")
    print("|---|" + "---|" * len(ROLES))
    for enq in enquiries:
        cells = []
        for role in ROLES:
            r = results[role][enq["id"]]
            d = r["obj"].get("decision") if isinstance(r["obj"], dict) else "unparsed"
            cells.append(f"{d} {'✓' if r['agrees_all'] else '✗'}")
        print(f"| {enq['id']} | " + " | ".join(cells) + " |")
    n = len(enquiries)
    for label, key in [("agrees with `expected`", "agrees_all"),
                       ("parsed", "parsed"), ("schema-valid", "valid")]:
        counts = [sum(1 for e in enquiries if results[role][e["id"]][key]) for role in ROLES]
        print(f"| **{label}** | " + " | ".join(f"{c}/{n}" for c in counts) + " |")


def field_movement(enquiries, results):
    moves = {f: [] for f in FIELDS}
    for enq in enquiries:
        base = results["policy_officer"][enq["id"]]["obj"]
        if not isinstance(base, dict):
            continue
        for role in ROLES[1:]:
            other = results[role][enq["id"]]["obj"]
            if not isinstance(other, dict):
                continue
            for f in FIELDS:
                if norm(f, other.get(f)) != norm(f, base.get(f)):
                    moves[f].append((enq["id"], role, base.get(f), other.get(f)))
    return moves


def print_movement(moves):
    print("\n### Which field moved, on which enquiry, under which role\n")
    print("| Field | Enquiries that moved | Role(s) that moved it |")
    print("|---|---|---|")
    for f in FIELDS:
        if not moves[f]:
            print(f"| `{f}` | none - moved on no enquiry | none |")
            continue
        enqs = sorted({m[0] for m in moves[f]})
        roles = sorted({m[1] for m in moves[f]}, key=ROLES.index)
        print(f"| `{f}` | {', '.join(enqs)} | {', '.join(roles)} |")
    print("\nDetail (policy_officer value -> other role's value):")
    for f in FIELDS:
        for eid, role, a, b in moves[f]:
            print(f"  {f:18} {eid}  {role:15} {fmt(a)} -> {fmt(b)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plain", action="store_true",
                    help="do not request JSON mode; rely on the prompt alone")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--out", default="easy_results.json",
                    help="file name under outputs/ for the raw replies")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set - copy .env.example to .env and add your key.")
    client = OpenAI()

    records, policy, enquiries = load("records.json"), load("policy.json"), load("enquiries.json")
    results: dict = {}
    tokens = {"prompt": 0, "completion": 0}

    for role in ROLES:
        system = build_system_prompt(role, records, policy)
        results[role] = {}
        print(f"running {role} ...", file=sys.stderr)
        for enq in enquiries:
            reply, (pt, ct) = call_model(client, args.model, system, enq["text"], json_mode=not args.plain)
            row = check(reply, enq["expected"])
            row["prompt_tokens"], row["completion_tokens"] = pt, ct
            tokens["prompt"] += pt or 0
            tokens["completion"] += ct or 0
            results[role][enq["id"]] = row

    print_summary_table(enquiries, results)
    moves = field_movement(enquiries, results)
    print_movement(moves)
    for role in ROLES:
        print_role_table(role, enquiries, results)

    for role in ROLES:
        for eid, r in results[role].items():
            if r["schema_errors"] or not r["parsed"]:
                print(f"\n[{role} {eid}] " + (r.get("parse_error") or "; ".join(r["schema_errors"])))

    print(f"\nTokens used: prompt {tokens['prompt']}, completion {tokens['completion']}")

    OUT.mkdir(exist_ok=True)
    out = OUT / args.out
    out.write_text(json.dumps({
        "model": args.model,
        "json_mode": not args.plain,
        "system_prompts": {r: build_system_prompt(r, records, policy) for r in ROLES},
        "results": {role: {eid: {k: v for k, v in r.items() if k != "obj"}
                           for eid, r in rows.items()} for role, rows in results.items()},
        "field_movement": {f: [list(m) for m in ms] for f, ms in moves.items()},
        "tokens": tokens,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw replies saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
