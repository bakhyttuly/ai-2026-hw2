# HW2 submission

**Name:** Bakdaulet
**Student ID:** 23068143
**Group:**
**Repository:** https://github.com/bakhyttuly/ai-2026-hw2

## AI tool disclosure

State which AI tools you used and for what. Expected and fine; undisclosed use
is not. If you used a model to help you draft a prompt, say which prompt.

> I used Claude to write the code for all three sublabs, including the system prompts (the four role prompts, the compress prompt, and the extraction and scoring prompts). I ran the programs myself with my own OpenAI key; all tables here are from those runs.

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
| `decision` | E-03, E-04, E-09 | front_desk |
| `amount` | none — moved on no enquiry | none |
| `missing_documents` | none — moved on no enquiry | none |

Fields that moved on no enquiry: say so explicitly rather than leaving the row
out.

### Raw replies

Paste the full reply for **one enquiry where a role changed the decision** away
from the policy officer's:

E-03, front_desk:

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
| **total for the run** | 5804 | 5662 |

The compress call itself: 1189 prompt tokens.

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
| story-01 | yes | yes | none | none |
| story-02 | yes | yes | graduation_year, gpa_4_scale, gpa_original, gpa_original_scale, experience_months_countable | no GPA |
| story-03 | yes | yes | none | GPA on 5.0 scale (4.6 → 3.68); paper under review |
| story-04 | yes | yes | none | papers not published (under review, in preparation) |
| story-05 | yes | yes | none | paper not published (in preparation) |
| story-06 | yes | yes | graduation_year, gpa_4_scale, gpa_original, gpa_original_scale | contradiction (GPA 3.2 vs 3.5, graduation 2024 vs 2026) |

The four traps, for reference: no GPA stated · a GPA on another scale · a paper
that is not published · a story that contradicts itself.

Paste the extraction for **story-06**, the one that contradicts itself:

```json
{
  "candidate_id": "story-06",
  "full_name": "Nurzhan Abilov",
  "story_language": "English",
  "degree": "BSc in Statistics",
  "graduation_year": null,
  "gpa_4_scale": null,
  "gpa_original": null,
  "gpa_original_scale": null,
  "languages": [
    "Kazakh",
    "Russian",
    "English"
  ],
  "published_outputs": [
    {
      "title_or_topic": "Survey weighting",
      "venue": "Peer-reviewed proceedings",
      "year": null,
      "status": "published",
      "peer_reviewed": true,
      "evidence": "one paper published, in a peer-reviewed proceedings, on survey weighting"
    }
  ],
  "published_peer_reviewed_count": 1,
  "unpublished_outputs": [
    {
      "title_or_topic": "Poster at a local event",
      "status": "poster",
      "evidence": "One poster at a local event, which I do not think counts."
    }
  ],
  "experience_periods": [
    {
      "role": "Insurance analytics team member",
      "start": "February 2023",
      "end": null,
      "months_stated": 40,
      "relevant": true,
      "countable": true,
      "note": "The story states about forty months; the first eight months were part-time and the remainder full-time.",
      "evidence": "I have been at an insurance analytics team since February 2023, which is about forty months. I was part-time for the first eight of those while I was still studying, then full-time."
    }
  ],
  "experience_months_countable": 40,
  "ambiguities": [
    "The GPA is contradictory: \"My GPA was 3.2\" and \"I think it was 3.5\"; therefore no GPA value or scale is selected.",
    "The graduation information is contradictory: \"I graduated in 2024 with a BSc in Statistics\" and \"I am currently a final-year student graduating in 2026\"; therefore graduation_year is null."
  ],
  "evidence": {
    "full_name": "Nurzhan Abilov",
    "degree": "I graduated in 2024 with a BSc in Statistics.",
    "graduation_year": null,
    "gpa": "My GPA was 3.2. Actually I should double-check that, I think it was 3.5",
    "languages": "Languages: Kazakh, Russian, English.",
    "experience_months_countable": "which is about forty months"
  }
}
```

### Part 2 — scores and the winner

| Candidate | academic (0–5) | research (0–5) | experience (0–5) | weighted total (code) |
|---|---|---|---|---|
| story-01 | 5 | 5 | 2 | 4.40 |
| story-02 | 0 | 1 | 0 | 0.30 |
| story-03 | 4 | 3 | 3 | 3.50 |
| story-04 | 4 | 3 | 5 | 3.90 |
| story-05 | 5 | 3 | 2 | 3.80 |
| story-06 | 1 | 3 | 5 | 2.40 |

**Winner, computed by my code:** story-01 (Aziza Bekova), 4.40

**The model's prose answer, asked separately ("who should win?"):**

> Aziza Bekova should win the scholarship. She has the strongest overall record: a 3.8/4.0 GPA, two published peer-reviewed papers, and eight months of relevant data work. Her limited experience is her main weakness, but the rubric gives academic record the greatest weight and research the second greatest; her perfect or near-perfect performance in those areas outweighs the shorter work history. Her weighted score is approximately **4.33/5**.
>
> The runner-up should be **Lyazzat Omarova**. Her 4.6/5.0 GPA converts to approximately 3.68/4.0, just below the rubric’s 3.7 threshold for the top academic score. She has one published peer-reviewed paper, a further paper under review that cannot be counted, and fourteen months of clearly dated relevant internships. Her record is well balanced, but she falls behind Aziza because she has only one published output and a slightly weaker converted academic result.
>
> Tamerlan Saparov is close behind, with two years of relevant experience but only one published paper and a 3.6/4.0 GPA. The other candidates either lack a usable GPA, have less research output, or have substantially less relevant experience.

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
