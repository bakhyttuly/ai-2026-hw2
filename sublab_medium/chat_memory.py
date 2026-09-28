"""Sublab Medium - memory you choose: the `compress` command.

Scripted comparison (both runs send the same twelve turns, then five probes):

    python -m sublab_medium.chat_memory

A real chat, where you can type `compress`, `tokens`, `state`, `history`, `quit`:

    python -m sublab_medium.chat_memory --interactive

What is sent on each call:
  * uncompressed: system message + every turn so far (grows forever)
  * compressed:   system message + the validated state object + the turns
                  since the last compression
If the summary does not parse or does not validate against
data/memory_state.schema.json, the history is KEPT and the program says so.
"""
from __future__ import annotations

import argparse
import copy
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
COMPRESS_MARKER = "<compress>"


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


STATE_SCHEMA = load("memory_state.schema.json")
STATE_VALIDATOR = Draft202012Validator(STATE_SCHEMA)
POLICY = load("policy.json")

# The assistant knows the RULE (so it can say what band 2 is worth), but it is
# deliberately NOT given the records: otherwise the probes about the missing
# document and the band could be answered by looking the applicant up, and they
# would stop measuring what the conversation memory kept.
ASSISTANT_SYSTEM = f"""You are the assistant of a university grant office, talking to one applicant.

The grant rule: {POLICY['rule_human']}
Amounts: band 1 -> 250,000 tenge, band 2 -> 150,000 tenge.

You do not have access to the applicant records. Rely only on what the
applicant has told you in this conversation (or in the conversation state, if
one is given). Never invent a fact the applicant did not state; if you do not
know something, say so. Answer briefly, in English, and when you mention an
amount write it in digits (for example 150,000)."""

COMPRESS_SYSTEM = f"""You compress a conversation between a grant-office assistant and an applicant
into ONE JSON object. Reply with the JSON object only - no markdown, no prose.

The object must match this JSON Schema exactly (all seven keys, no others):
{json.dumps(STATE_SCHEMA, ensure_ascii=False, indent=1)}

Rules:
- applicant_id: the id the applicant gave (e.g. "A-202"), or null if never given.
- topic: one short line on what the conversation is about.
- facts: things the APPLICANT stated about themselves, one fact per string, with
  names, numbers and document names kept verbatim (e.g. "income band is 2",
  "could not upload id card - scanner broke"). Keep every fact, even one that
  seems minor or unrelated to the decision (family members, earlier years).
- decisions: what the office has said or concluded so far (e.g. the amount the
  rule gives, what is still missing). Only what was actually said.
- constraints: conditions on how or when things can happen that the applicant
  set (days they can come, deadlines, what they cannot do).
- open_questions: every question the applicant asked that has NOT been fully
  answered yet, phrased so it can be answered later.
- language: the language(s) the applicant writes in.
Nothing may be invented: a fact that was never said is not a fact. Arrays are
empty rather than omitted."""


def call_model(client, model, messages, json_mode=False):
    kwargs = dict(model=model, messages=messages)
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
    return (resp.choices[0].message.content or "",
            u.prompt_tokens if u else None,
            u.completion_tokens if u else None)


class Session:
    """One conversation. `history` is what gets resent; `state` replaces it after compress."""

    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.history: list[dict] = []
        self.state: dict | None = None
        self.log: list[dict] = []        # one entry per call, for the tables
        self.last_usage: dict | None = None

    def messages(self) -> list[dict]:
        msgs = [{"role": "system", "content": ASSISTANT_SYSTEM}]
        if self.state is not None:
            msgs.append({"role": "system", "content":
                         "Conversation state so far (the earlier turns were compressed "
                         "into this object; treat it as what was said):\n"
                         + json.dumps(self.state, ensure_ascii=False, indent=1)})
        return msgs + self.history

    def say(self, text: str, kind="turn") -> str:
        self.history.append({"role": "user", "content": text})
        msgs = self.messages()
        reply, pt, ct = call_model(self.client, self.model, msgs)
        self.history.append({"role": "assistant", "content": reply})
        entry = {"kind": kind, "user": text, "reply": reply, "prompt_tokens": pt,
                 "completion_tokens": ct, "messages_sent": len(msgs),
                 "compressed": self.state is not None}
        self.log.append(entry)
        self.last_usage = entry
        return reply

    def ask_without_remembering(self, text: str):
        """Probe: ask from the current memory, but do not add the probe to it."""
        saved = copy.deepcopy(self.history)
        try:
            reply = self.say(text, kind="probe")
        finally:
            self.history = saved
        return reply, self.log[-1]

    def compress(self) -> tuple[bool, str]:
        """Summarise into a state object. Only replace history if it validates."""
        transcript = []
        if self.state is not None:
            transcript.append("EARLIER STATE: " + json.dumps(self.state, ensure_ascii=False))
        for m in self.history:
            who = "APPLICANT" if m["role"] == "user" else "ASSISTANT"
            transcript.append(f"{who}: {m['content']}")
        msgs = [{"role": "system", "content": COMPRESS_SYSTEM},
                {"role": "user", "content": "Conversation to compress:\n\n" + "\n\n".join(transcript)}]
        raw, pt, ct = call_model(self.client, self.model, msgs, json_mode=True)
        entry = {"kind": "compress", "reply": raw, "prompt_tokens": pt,
                 "completion_tokens": ct, "messages_sent": len(msgs)}
        self.log.append(entry)
        self.last_usage = entry
        try:
            state = json.loads(raw)
        except json.JSONDecodeError as e:
            entry["ok"] = False
            return False, f"summary did not parse ({e}); history kept, {len(self.history)} messages"
        errors = list(STATE_VALIDATOR.iter_errors(state))
        if errors:
            entry["ok"] = False
            msg = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
            return False, f"summary failed the schema ({msg}); history kept, {len(self.history)} messages"
        dropped = len(self.history)
        self.state = state
        self.history = []
        entry["ok"] = True
        entry["state"] = state
        return True, f"compressed: {dropped} messages replaced by the state object"


# --------------------------------------------------------------------------
# Probe checking
# --------------------------------------------------------------------------
def retrieved(answer: str, expect_contains: list[str]) -> tuple[bool, str | None]:
    """Any one of the expected strings counts. Case-insensitive; digit groups
    written with spaces or commas ("150 000") are normalised too."""
    low = answer.lower()
    squashed = re.sub(r"(?<=\d)[\s,.  ](?=\d{3})", "", low)
    for s in expect_contains:
        s_low = s.lower()
        if s_low in low or s_low in squashed:
            return True, s
    return False, None


# --------------------------------------------------------------------------
# Scripted run
# --------------------------------------------------------------------------
def scripted_run(client, model, script, do_compress: bool):
    s = Session(client, model)
    compress_note = None
    for turn in script["conversation"]:
        if turn == COMPRESS_MARKER:
            if do_compress:
                ok, compress_note = s.compress()
                print(f"  [compress] {compress_note}", file=sys.stderr)
            continue
        s.say(turn)
    probes = []
    for p in script["probes"]:
        reply, entry = s.ask_without_remembering(p["question"])
        ok, matched = retrieved(reply, p["expect_contains"])
        probes.append({**p, "answer": reply, "retrieved": ok, "matched": matched,
                       "prompt_tokens": entry["prompt_tokens"]})
    return s, probes, compress_note


def short(text, n=90):
    t = " ".join(str(text).split()).replace("|", "/")
    return t if len(t) <= n else t[: n - 1] + "…"


def print_tables(runA, runB):
    sA, pA, _ = runA
    sB, pB, noteB = runB
    turnsA = [e for e in sA.log if e["kind"] == "turn"]
    turnsB = [e for e in sB.log if e["kind"] == "turn"]
    compB = [e for e in sB.log if e["kind"] == "compress"]

    print("\n### Tokens per call (prompt tokens sent)\n")
    print("| Call | A — never compressed | B — compressed at the `compress` turn |")
    print("|---|---|---|")
    for i in range(max(len(turnsA), len(turnsB))):
        a = turnsA[i]["prompt_tokens"] if i < len(turnsA) else ""
        b = turnsB[i]["prompt_tokens"] if i < len(turnsB) else ""
        flag = " (after compress)" if i < len(turnsB) and turnsB[i]["compressed"] else ""
        print(f"| {i + 1} | {a} | {b}{flag} |")
    peakA = max(e["prompt_tokens"] or 0 for e in turnsA)
    peakB = max(e["prompt_tokens"] or 0 for e in turnsB)
    totA = sum(e["prompt_tokens"] or 0 for e in turnsA)
    totB = sum(e["prompt_tokens"] or 0 for e in turnsB)
    print(f"| **peak** | {peakA} | {peakB} |")
    print(f"| **total for the run** | {totA} | {totB} |")
    for c in compB:
        print(f"\nThe compress call itself (B only, not in the 12): prompt {c['prompt_tokens']}, "
              f"completion {c['completion_tokens']}, ok={c.get('ok')}. "
              f"Total for B including it: {totB + (c['prompt_tokens'] or 0)} prompt tokens.")
    print(f"B compress result: {noteB}")

    print("\n### Probes after the conversation\n")
    print("| Probe | Tests | A retrieved? | A answer | B retrieved? | B answer |")
    print("|---|---|---|---|---|---|")
    for a, b in zip(pA, pB):
        print(f"| {a['id']} | {short(a['tests'], 40)} | {'yes' if a['retrieved'] else 'LOST'} | "
              f"{short(a['answer'])} | {'yes' if b['retrieved'] else 'LOST'} | {short(b['answer'])} |")
    print(f"| **retrieved** | | {sum(p['retrieved'] for p in pA)}/5 | | "
          f"{sum(p['retrieved'] for p in pB)}/5 | |")
    print("\nProbe prompt tokens: A " + ", ".join(str(p["prompt_tokens"]) for p in pA)
          + " | B " + ", ".join(str(p["prompt_tokens"]) for p in pB))

    print("\n### The state my compression produced\n")
    print("```json")
    print(json.dumps(sB.state, ensure_ascii=False, indent=2) if sB.state else
          "(no valid state - see the compress result above)")
    print("```")


def run_scripted(client, model):
    script = load("chat_script.json")
    print("run A (compress skipped) ...", file=sys.stderr)
    runA = scripted_run(client, model, script, do_compress=False)
    print("run B (compress acts) ...", file=sys.stderr)
    runB = scripted_run(client, model, script, do_compress=True)
    print_tables(runA, runB)

    OUT.mkdir(exist_ok=True)
    out = OUT / "medium_results.json"
    out.write_text(json.dumps({
        "model": model,
        "A": {"calls": runA[0].log, "probes": runA[1]},
        "B": {"calls": runB[0].log, "probes": runB[1], "state": runB[0].state},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull transcripts saved to {out.relative_to(ROOT)}")


# --------------------------------------------------------------------------
# Interactive
# --------------------------------------------------------------------------
HELP = ("commands: compress | tokens (what the last call cost) | state | "
        "history | help | quit")


def run_interactive(client, model):
    s = Session(client, model)
    print("Grant office chat. " + HELP)
    while True:
        try:
            text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        cmd = text.lower()
        if cmd in ("quit", "exit"):
            break
        if cmd == "help":
            print(HELP)
            continue
        if cmd == "compress":
            ok, note = s.compress()
            print(("OK  " if ok else "FAILED  ") + note)
            if ok:
                print(json.dumps(s.state, ensure_ascii=False, indent=2))
            continue
        if cmd == "tokens":
            u = s.last_usage
            if not u:
                print("no calls yet")
            else:
                print(f"last call ({u['kind']}): sent {u['prompt_tokens']} prompt tokens in "
                      f"{u['messages_sent']} messages, got {u['completion_tokens']} back")
                total = sum(e["prompt_tokens"] or 0 for e in s.log)
                print(f"session total: {total} prompt tokens over {len(s.log)} calls")
            continue
        if cmd == "state":
            print(json.dumps(s.state, ensure_ascii=False, indent=2) if s.state else "no state yet (never compressed)")
            continue
        if cmd == "history":
            for m in s.messages():
                print(f"  [{m['role']}] {short(m['content'], 100)}")
            continue
        reply = s.say(text)
        u = s.last_usage
        print(f"assistant> {reply}")
        print(f"  (sent {u['prompt_tokens']} tokens in {u['messages_sent']} messages"
              f"{', from compressed state' if u['compressed'] else ''})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set - copy .env.example to .env and add your key.")
    client = OpenAI()
    if args.interactive:
        run_interactive(client, args.model)
    else:
        run_scripted(client, args.model)


if __name__ == "__main__":
    main()
