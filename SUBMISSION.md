# HW2 submission

**Name:**
**Student ID:**
**Group:**
**Repository:**

## AI tool disclosure

State which AI tools you used and for what. Expected and fine; undisclosed use
is not. If you used a model to help you draft a prompt, say which prompt.

>

---

## Sublab Easy — one task, four roles

### Decisions per role

One row per enquiry. In each cell write the `decision` your run returned, and
whether it agrees with `expected` in `data/enquiries.json`:

| Enquiry | policy_officer | front_desk | auditor | bilingual_clerk |
|---|---|---|---|---|
| E-01 | granted ✓ | granted ✓ | granted ✓ | granted ✓ |
| E-02 | more_info ✓ | more_info ✓ | more_info ✓ | more_info ✓ |
| E-03 | refused ✓ | more_info ✗ | refused ✓ | refused ✓ |
| E-04 | refused ✓ | more_info ✗ | refused ✓ | refused ✓ |
| E-05 | granted ✓ | granted ✓ | granted ✓ | granted ✓ |
| E-06 | granted ✓ | granted ✓ | granted ✓ | granted ✓ |
| E-07 | granted ✓ | granted ✓ | granted ✓ | granted ✓ |
| E-08 | not_found ✓ | not_found ✓ | not_found ✓ | not_found ✓ |
| E-09 | refused ✓ | more_info ✗ | refused ✓ | refused ✓ |
| E-10 | more_info ✓ | more_info ✓ | more_info ✓ | more_info ✓ |
| **agrees with `expected`** | 10/10 | 7/10 | 10/10 | 10/10 |
| **parsed** | 10/10 | 10/10 | 10/10 | 10/10 |
| **schema-valid** | 10/10 | 10/10 | 10/10 | 10/10 |

### Which field moved, on which enquiry, under which role

| Field | Enquiries that moved | Role(s) that moved it |
|---|---|---|
| `found` | none — moved on no enquiry | none |
| `decision` | E-03, E-04, E-09 (refused → more_info) | front_desk |
| `amount` | none — moved on no enquiry | none |
| `missing_documents` | none — moved on no enquiry | none |

Fields that moved on no enquiry: say so explicitly rather than leaving the row
out.

`found`, `amount` and `missing_documents` moved on no enquiry under any role.
The auditor moved nothing (10/10 identical to the policy officer). The
bilingual clerk moved no structured field; only `reason` differs. `reason` on
E-07 came back in Kazakh under all four roles, not only the bilingual clerk.

Model `gpt-5.6-luna`, JSON mode on. Run 2 of 2: in run 1 the shared part of the
system prompt defined `refused`/`granted` in terms of the rule, and all four
roles returned identical decisions on all ten enquiries (40/40 agree). Run 2
removed that from the shared block; the tables above are run 2.

### Raw replies

Paste the full reply for **one enquiry where a role changed the decision** away
from the policy officer's:

E-03 (Madina Zhangeldi, GPA 2.4), `front_desk` — the policy officer returned `refused`:

```
{"applicant_id":"A-203","found":true,"decision":"more_info","amount":0,"missing_documents":[],"reason":"The recorded GPA is 2.4, below the required minimum of 2.67. Please return with an updated transcript showing a GPA of at least 2.67."}
```

Paste the full reply for **E-07 (the Kazakh enquiry)** from the bilingual
clerk, so the `reason` language is visible:

```
{"applicant_id":"A-201","found":true,"decision":"granted","amount":250000,"missing_documents":[],"reason":"Сіздің GPA көрсеткіші 3.4, табыс санатыңыз 1 және қажетті құжаттардың екеуі де тіркелген. Сізге 250000 теңге грант тағайындалады."}
```

### Written answers

**1. Which fields are role-sensitive and which are not?** Point at rows in your
tables.

>

**2. Which enquiries are most sensitive to the role, and why those?** Say what
E-03, E-04, E-07 and E-10 are each testing.

>

**3. Where does discretion belong — the role paragraph, or code that reads
`decision` afterwards?** Say what a downstream program can and cannot tell
about which role produced a record.

>

**4. Is a role a boundary?** Say in Week 2 terms what the role paragraph is
made of, and what you would put in code — not in the prompt — if a wrong
`decision` were expensive.

>

---

## Sublab Medium — memory you choose

### Tokens per call

| Call | A — never compressed | B — compressed at the `compress` turn |
|---|---|---|
| 1 | 249 | 249 |
| 2 | 297 | 310 |
| 3 | 356 | 363 |
| 4 | 405 | 434 |
| 5 | 450 | 480 |
| 6 | 522 | 539 |
| 7 | 593 | 609 |
| 8 | 652 | 674 |
| 9 | 708 | 739 |
| 10 | 757 | 609 (after compress) |
| 11 | 815 | 656 (after compress) |
| 12 | — | — |
| **peak** | 815 | 739 |
| **total for the run** | 5804 | 5662 (6851 incl. the compress call) |

Prompt tokens per call, model `gpt-5.6-luna`. The script has twelve entries,
one of which is `<compress>`, so each run sends eleven applicant turns; row 12
is empty in both. The compress call itself (run B only) sent 1189 prompt
tokens and got 692 back; it is not one of the eleven. B's calls 2–9 are higher
than A's even though nothing was compressed yet: the assistant's replies
differ between runs, and they are resent too.

### Probes after the conversation

| Probe | Tests | A retrieved? | A answer | B retrieved? | B answer |
|---|---|---|---|---|---|
| Q-1 identity | turn 1 | yes | You are Daniyar Qoshan, applicant A-202. | yes | You are Daniyar Qoshan, applicant **A-202**. |
| Q-2 missing document | turn 5 | yes | Based on what you told me, your ID card has not been uploaded. I cannot verify the file r… | yes | Your **ID card** is still missing from your file. |
| Q-3 band and amount | turns 3–4 | yes | I cannot verify your income band from the records. If it is band 2 and you meet all requi… | yes | Your stated income band is 2. If you qualify, the grant amount would be **150,000 tenge**. |
| Q-4 the constraint | turn 6 | yes | You said you can come to the office on Thursdays. | yes | You can come to the office on **Thursday**. |
| Q-5 the open question | turn 7 | yes | You asked whether a scanned letter from your employer would count or whether the original… | yes | You asked whether a scanned letter from your employer would be accepted or whether the or… |
| **retrieved** | | 5/5 | | 5/5 | |

### The state my compression produced

It parsed and validated against `data/memory_state.schema.json` on the first try, and replaced 18 messages (9 turns + 9 replies).

```json
{
  "applicant_id": "A-202",
  "topic": "Study grant eligibility and document submission",
  "facts": [
    "name is Daniyar Qoshan",
    "sent my transcript last week",
    "income band is 2",
    "my family's certificate says so",
    "could not upload my id card because the scanner at home broke",
    "have lab all week otherwise",
    "sister Aruzhan applied last year and she is on file too"
  ],
  "decisions": [
    "Eligibility cannot be determined from the information provided.",
    "If the applicant qualifies under income band 2, the grant amount is 150,000 tenge.",
    "Eligibility depends on a verified GPA of at least 2.67, income band 2, and both required documents being on file.",
    "If the id card is not on file, the applicant would not qualify until it is submitted and recorded.",
    "The id card can be brought to the office on Thursday for submission and verification.",
    "The grant rule does not specify whether a scanned employer letter or the original is required.",
    "A same-day decision cannot be confirmed; processing time is not specified.",
    "Aruzhan's application does not affect the applicant's eligibility."
  ],
  "constraints": [
    "can only come to the office on Thursdays"
  ],
  "open_questions": [
    "Does the applicant qualify for the study grant?",
    "Does a scanned letter from the employer count, or is the original required?",
    "If the applicant brings the id card on Thursday, will the decision be made the same day?"
  ],
  "language": "Kazakh and English"
}
```

### Written answers

**1. What did compression buy?** Peak tokens both ways, probes retrieved both
ways, and — if a probe was lost — which one and which turn it came from.

>

**2. Why must the state be structured rather than a paragraph?** You could have
asked for "a summary". Say what changes when the summary is an object with
named fields.

>

**3. What is missing from your state that you would add?** Name what you would
add and what you would drop to pay for it.

>

**4. When is compression the wrong choice?** Name a conversation where it would
lose something that cannot be recovered, and say whether your program would
notice.

>

---

## Sublab Hard — stories in, CVs out, the best candidate by code

### Part 1 — extraction

| Story | Parsed? | Valid? | Fields that came back `null` | Traps hit |
|---|---|---|---|---|
| story-01 | | | | |
| story-02 | | | | |
| story-03 | | | | |
| story-04 | | | | |
| story-05 | | | | |
| story-06 | | | | |

The four traps, for reference: no GPA stated · a GPA on another scale · a paper
that is not published · a story that contradicts itself.

Paste the extraction for **story-06**, the one that contradicts itself:

```json
```

### Part 2 — scores and the winner

| Candidate | academic (0–5) | research (0–5) | experience (0–5) | weighted total (code) |
|---|---|---|---|---|
| story-01 | | | | |
| story-02 | | | | |
| story-03 | | | | |
| story-04 | | | | |
| story-05 | | | | |
| story-06 | | | | |

**Winner, computed by my code:**

**The model's prose answer, asked separately ("who should win?"):**

>
```

### Part 3 — written answers

**1. Which rule did you have to add, and what broke without it?** Name the
story that forced it.

>

**2. Where did the model guess, and where did your code have to decide?** One
example of each, from your run.

>

**3. Did your prose ranking and your computed ranking agree?** Say which one
you trust and why — and if they agreed, what you would need to see before
trusting the prose one alone.

>

**4. The rubric has no anchor for a contradicted field.** The stories say 3.2
and then 3.5; the rubric defines a 0 and a 5 and nothing in between for this
case. Say what you did and what the rule should be.

>

**5. How close were your top two candidates?** If they were within 0.05, say
what you would tell the committee and what you would change in the extraction
to make that call defensible.

>

---

## Reflection (optional, one short paragraph)

Having now written a role prompt, compressed a conversation, and ranked six
extractions — what will you do differently the next time you build something
that has to get reliable structured output out of a model?

>
