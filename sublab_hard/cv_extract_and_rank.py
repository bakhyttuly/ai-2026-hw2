from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from openai import BadRequestError, OpenAI

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "outputs"
MODEL = "gpt-5.6-luna"

RUBRIC = json.loads((DATA / "candidate_rubric.json").read_text(encoding="utf-8"))
WEIGHTS = {c["id"]: c["weight"] for c in RUBRIC["criteria"]}
CRITERIA = list(WEIGHTS)
PUBLISHED_STATUSES = {"published", "accepted"}

NULLABLE_STR = {"type": ["string", "null"]}
EVIDENCE = {"type": ["string", "null"],
            "description": "verbatim quote from the story, or null"}

CV_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_id": {"type": "string"},
        "full_name": NULLABLE_STR,
        "story_language": {"type": "string"},
        "degree": NULLABLE_STR,
        "graduation_year": {"type": ["integer", "null"]},
        "gpa_4_scale": {"type": ["number", "null"], "minimum": 0, "maximum": 4},
        "gpa_original": {"type": ["number", "null"]},
        "gpa_original_scale": {"type": ["number", "null"]},
        "languages": {"type": "array", "items": {"type": "string"}},
        "published_outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title_or_topic": {"type": "string"},
                    "venue": NULLABLE_STR,
                    "year": {"type": ["integer", "null"]},
                    "status": {"enum": ["published", "accepted"]},
                    "peer_reviewed": {"type": ["boolean", "null"]},
                    "evidence": {"type": "string"},
                },
                "required": ["title_or_topic", "venue", "year", "status",
                             "peer_reviewed", "evidence"],
                "additionalProperties": False,
            },
        },
        "published_peer_reviewed_count": {"type": ["integer", "null"], "minimum": 0},
        "unpublished_outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title_or_topic": {"type": "string"},
                    "status": {"type": "string",
                               "description": "submitted / under review / in preparation / in press / planned / poster / other"},
                    "evidence": {"type": "string"},
                },
                "required": ["title_or_topic", "status", "evidence"],
                "additionalProperties": False,
            },
        },
        "experience_periods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "start": NULLABLE_STR,
                    "end": NULLABLE_STR,
                    "months_stated": {"type": ["integer", "null"]},
                    "relevant": {"type": ["boolean", "null"]},
                    "countable": {"type": "boolean"},
                    "note": NULLABLE_STR,
                    "evidence": {"type": "string"},
                },
                "required": ["role", "start", "end", "months_stated", "relevant",
                             "countable", "note", "evidence"],
                "additionalProperties": False,
            },
        },
        "experience_months_countable": {"type": ["integer", "null"], "minimum": 0},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "object",
            "properties": {k: EVIDENCE for k in [
                "full_name", "degree", "graduation_year", "gpa",
                "languages", "experience_months_countable"]},
            "required": ["full_name", "degree", "graduation_year", "gpa",
                         "languages", "experience_months_countable"],
            "additionalProperties": False,
        },
    },
    "required": ["candidate_id", "full_name", "story_language", "degree",
                 "graduation_year", "gpa_4_scale", "gpa_original",
                 "gpa_original_scale", "languages", "published_outputs",
                 "published_peer_reviewed_count", "unpublished_outputs",
                 "experience_periods", "experience_months_countable",
                 "ambiguities", "evidence"],
    "additionalProperties": False,
}
CV_VALIDATOR = Draft202012Validator(CV_SCHEMA)

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_id": {"type": "string"},
        **{c: {"type": "integer", "minimum": 0, "maximum": 5} for c in CRITERIA},
        "justification": {
            "type": "object",
            "properties": {c: {"type": "string"} for c in CRITERIA},
            "required": CRITERIA,
            "additionalProperties": False,
        },
    },
    "required": ["candidate_id", *CRITERIA, "justification"],
    "additionalProperties": False,
}
SCORE_VALIDATOR = Draft202012Validator(SCORE_SCHEMA)

EXTRACT_SYSTEM = f"""You extract a structured CV from a scholarship candidate's written story.
Reply with ONE JSON object only (no markdown, no prose) matching this JSON Schema:
{json.dumps(CV_SCHEMA, ensure_ascii=False)}

EXTRACTION RULES - follow every one:
1. NULL, NEVER ESTIMATED. A fact the story does not state is null. Never estimate
   or infer it from the degree, the university, honours ("with distinction"),
   or the impression the story gives. No GPA stated means gpa_4_scale,
   gpa_original and gpa_original_scale are all null.
2. OTHER SCALES. A GPA on a scale other than 4.0 is converted linearly to the
   4.0 scale (gpa_4_scale = gpa_original / gpa_original_scale * 4, rounded to
   two decimals), and the original value and scale are recorded in
   gpa_original and gpa_original_scale. A GPA already on 4.0 has
   gpa_original_scale 4. If the story gives a GPA but not its scale, record
   gpa_original, leave the scale and gpa_4_scale null, and add an ambiguity.
3. PUBLISHED MEANS PUBLISHED. A paper is published only when the story says it
   is published or accepted. "Submitted", "under review", "in preparation",
   "in press", "planned", "being written", posters and talks are NOT published:
   put them in unpublished_outputs with their status and do NOT count them.
   published_peer_reviewed_count counts only published_outputs that the story
   presents as peer-reviewed.
4. CONTRADICTIONS ARE NOT RESOLVED. If the story gives two incompatible values
   for the same fact (two GPAs, two graduation years, a month count that does
   not match the dates), do not pick one and do not average them: set the field
   to null and describe the contradiction, quoting both values, in ambiguities.
5. EXPERIENCE. Count months, not jobs. Overlapping periods count once. A period
   with no start/end dates is not countable (countable=false) - record it and
   say why in note. Only directly relevant work or internships count toward
   experience_months_countable (mark each period's relevance). If no period is
   countable, experience_months_countable is 0 when the story mentions no work
   at all, and null when work is mentioned but cannot be counted.
6. EVIDENCE. For every field you fill, give a short verbatim quote from the
   story in the original language. A null field has null evidence.
7. Write the extracted values in English even when the story is in another
   language, but keep the evidence quotes verbatim. Record story_language.
"""

SCORE_SYSTEM = f"""You score one scholarship candidate against a rubric, from their extracted CV.
Reply with ONE JSON object only, matching this JSON Schema:
{json.dumps(SCORE_SCHEMA)}

The rubric (criteria, what 0 and 5 mean, counting rules):
{json.dumps(RUBRIC, ensure_ascii=False, indent=1)}

Give each criterion an integer from 0 to 5 and a one-sentence justification.
Do NOT compute a weighted total, a rank or a recommendation - only the three
scores. Score from the CV record only; a null field is information that was
not stated (or was contradicted), and must not be filled in by guessing.
"""

PROSE_SYSTEM = """You advise a scholarship committee. There is one funded place and six
candidates. Read the rubric and the six written applications, and answer in
prose: which candidate should win, and why? Name the runner-up too."""


def call_model(client, model, system, user, json_mode=True):
    kwargs = dict(model=model, messages=[{"role": "system", "content": system},
                                         {"role": "user", "content": user}])
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except BadRequestError:
        if not json_mode:
            raise
        kwargs.pop("response_format")
        resp = client.chat.completions.create(**kwargs)
    u = resp.usage
    return resp.choices[0].message.content or "", (u.prompt_tokens if u else 0,
                                                    u.completion_tokens if u else 0)


def parse_and_validate(raw, validator):
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, False, False, [f"parse error: {e}"]
    errs = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(obj)]
    return obj, True, not errs, errs


def load_stories():
    return {p.stem: p.read_text(encoding="utf-8")
            for p in sorted((DATA / "candidates").glob("story-*.md"))}


TOP_LEVEL_NULLABLE = ["full_name", "degree", "graduation_year", "gpa_4_scale",
                      "gpa_original", "gpa_original_scale",
                      "published_peer_reviewed_count", "experience_months_countable"]


def code_checks(cv: dict) -> list[str]:
    notes = []
    orig, scale, g4 = cv.get("gpa_original"), cv.get("gpa_original_scale"), cv.get("gpa_4_scale")
    if orig is not None and scale:
        expected = round(orig / scale * 4, 2)
        if g4 is None:
            notes.append(f"gpa: original {orig}/{scale} given but gpa_4_scale null")
        elif abs(expected - g4) > 0.011:
            notes.append(f"gpa: model converted {orig}/{scale} to {g4}, code gets {expected}")
    pubs = cv.get("published_outputs") or []
    counted = sum(1 for p in pubs if p.get("status") in PUBLISHED_STATUSES
                  and p.get("peer_reviewed") is not False)
    if cv.get("published_peer_reviewed_count") not in (None, counted):
        notes.append(f"publications: model says {cv['published_peer_reviewed_count']}, "
                     f"list gives {counted}")
    periods = [p for p in cv.get("experience_periods") or []
               if p.get("countable") and p.get("relevant") and p.get("months_stated")]
    summed = sum(p["months_stated"] for p in periods)
    if cv.get("experience_months_countable") not in (None, summed) and periods:
        notes.append(f"experience: model says {cv['experience_months_countable']}, "
                     f"countable periods sum to {summed} (before overlap removal)")
    return notes


def traps_hit(cv: dict) -> list[str]:
    traps = []
    if cv.get("gpa_original") is None and cv.get("gpa_4_scale") is None and not any(
            "gpa" in a.lower() for a in cv.get("ambiguities", [])):
        traps.append("no GPA stated → null")
    if cv.get("gpa_original_scale") not in (None, 4, 4.0):
        traps.append(f"GPA on {cv['gpa_original_scale']}-scale → converted to {cv.get('gpa_4_scale')}")
    if cv.get("unpublished_outputs"):
        statuses = ", ".join(u["status"] for u in cv["unpublished_outputs"])
        traps.append(f"unpublished not counted ({statuses})")
    if cv.get("ambiguities"):
        traps.append(f"contradiction/ambiguity recorded ({len(cv['ambiguities'])})")
    return traps or ["none"]


def weighted_total(scores: dict) -> float:
    return round(sum(WEIGHTS[c] * scores[c] for c in CRITERIA), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set - copy .env.example to .env and add your key.")
    client = OpenAI()
    stories = load_stories()
    tokens = [0, 0]

    def use(t):
        tokens[0] += t[0] or 0
        tokens[1] += t[1] or 0

    cvs, extraction = {}, {}
    for sid, text in stories.items():
        print(f"extracting {sid} ...", file=sys.stderr)
        raw, t = call_model(client, args.model, EXTRACT_SYSTEM,
                            f"candidate_id: {sid}\n\nSTORY:\n{text}")
        use(t)
        cv, parsed, valid, errs = parse_and_validate(raw, CV_VALIDATOR)
        extraction[sid] = {"raw": raw, "parsed": parsed, "valid": valid, "errors": errs,
                           "cv": cv}
        if isinstance(cv, dict):
            extraction[sid]["nulls"] = [f for f in TOP_LEVEL_NULLABLE if cv.get(f) is None]
            extraction[sid]["traps"] = traps_hit(cv)
            extraction[sid]["code_checks"] = code_checks(cv)
            if valid:
                cvs[sid] = cv

    print("\n### Part 1 — extraction\n")
    print("| Story | Parsed? | Valid? | Fields that came back `null` | Traps hit |")
    print("|---|---|---|---|---|")
    for sid, e in extraction.items():
        print(f"| {sid} | {'yes' if e['parsed'] else 'NO'} | {'yes' if e['valid'] else 'NO'} | "
              f"{', '.join(e.get('nulls', [])) or 'none'} | {'; '.join(e.get('traps', ['-']))} |")
    for sid, e in extraction.items():
        if e["errors"]:
            print(f"\n[{sid}] schema/parse errors: " + "; ".join(e["errors"][:5]))
        if e.get("code_checks"):
            print(f"[{sid}] code disagrees with model: " + "; ".join(e["code_checks"]))

    print("\nKey extracted values:")
    print("| Story | name | degree | grad | GPA (4.0) | original | published | months | ambiguities |")
    print("|---|---|---|---|---|---|---|---|---|")
    for sid, e in extraction.items():
        cv = e["cv"] if isinstance(e["cv"], dict) else {}
        orig = (f"{cv.get('gpa_original')}/{cv.get('gpa_original_scale')}"
                if cv.get("gpa_original") is not None else "null")
        amb = " / ".join(cv.get("ambiguities", [])).replace("|", "/")
        print(f"| {sid} | {cv.get('full_name')} | {cv.get('degree')} | {cv.get('graduation_year')} | "
              f"{cv.get('gpa_4_scale')} | {orig} | {cv.get('published_peer_reviewed_count')} | "
              f"{cv.get('experience_months_countable')} | {amb or '-'} |")

    if "story-06" in extraction:
        print("\nExtraction for story-06 (the one that contradicts itself):\n```json")
        print(json.dumps(extraction["story-06"]["cv"], ensure_ascii=False, indent=2)
              if extraction["story-06"]["cv"] else extraction["story-06"]["raw"])
        print("```")

    scores = {}
    for sid, cv in cvs.items():
        print(f"scoring {sid} ...", file=sys.stderr)
        raw, t = call_model(client, args.model, SCORE_SYSTEM,
                            "Extracted CV:\n" + json.dumps(cv, ensure_ascii=False, indent=1))
        use(t)
        obj, parsed, valid, errs = parse_and_validate(raw, SCORE_VALIDATOR)
        scores[sid] = {"raw": raw, "parsed": parsed, "valid": valid, "errors": errs, "obj": obj}
        if valid:
            scores[sid]["total"] = weighted_total(obj)

    ranked = sorted((sid for sid in scores if "total" in scores[sid]),
                    key=lambda s: scores[s]["total"], reverse=True)

    print("\n### Part 2 — scores and the winner\n")
    print("| Candidate | academic (0–5) | research (0–5) | experience (0–5) | weighted total (code) |")
    print("|---|---|---|---|---|")
    for sid in stories:
        s = scores.get(sid)
        if not s or not s["valid"]:
            why = "not extracted" if not s else "; ".join(s["errors"][:2])
            print(f"| {sid} | - | - | - | invalid ({why}) |")
            continue
        o = s["obj"]
        print(f"| {sid} | {o['academic']} | {o['research']} | {o['experience']} | {s['total']:.2f} |")

    print("\nJustifications:")
    for sid in ranked:
        j = scores[sid]["obj"]["justification"]
        print(f"  {sid}: " + " | ".join(f"{c}: {j[c]}" for c in CRITERIA))

    winner_line = "no valid scores"
    if ranked:
        top = scores[ranked[0]]["total"]
        tied = [s for s in ranked if scores[s]["total"] == top]
        name = lambda s: (cvs[s].get("full_name") or "?")
        if len(tied) > 1:
            winner_line = "TIE between " + ", ".join(f"{s} ({name(s)})" for s in tied) + f" at {top:.2f}"
        else:
            winner_line = f"{ranked[0]} ({name(ranked[0])}) with {top:.2f}"
        print(f"\n**Winner, computed by my code:** {winner_line}")
        print("Ranking: " + " > ".join(f"{s} {scores[s]['total']:.2f}" for s in ranked))
        if len(ranked) > 1:
            gap = round(scores[ranked[0]]["total"] - scores[ranked[1]]["total"], 2)
            print(f"Gap between #1 and #2: {gap:.2f}"
                  + ("  <-- within 0.05: too close to call on these scores" if gap <= 0.05 else ""))

    print("\nasking for the prose recommendation ...", file=sys.stderr)
    stories_block = "\n\n".join(f"===== {sid} =====\n{text}" for sid, text in stories.items())
    prose, t = call_model(client, args.model, PROSE_SYSTEM,
                          "RUBRIC:\n" + json.dumps(RUBRIC, ensure_ascii=False, indent=1)
                          + "\n\nAPPLICATIONS:\n\n" + stories_block, json_mode=False)
    use(t)
    print("\n**The model's prose answer, asked separately (\"who should win?\"):**\n")
    print(prose)

    print(f"\nTokens used: prompt {tokens[0]}, completion {tokens[1]}")
    OUT.mkdir(exist_ok=True)
    out = OUT / "hard_results.json"
    out.write_text(json.dumps({
        "model": args.model,
        "extraction": extraction,
        "scores": scores,
        "ranking": [(s, scores[s]["total"]) for s in ranked],
        "winner": winner_line,
        "prose": prose,
        "tokens": tokens,
        "prompts": {"extract": EXTRACT_SYSTEM, "score": SCORE_SYSTEM, "prose": PROSE_SYSTEM},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Everything saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
