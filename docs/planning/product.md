---
type: project
status: active
owner: Owen
started: 2026-06-15
due: 2026-06-21
tags: [hackathon, ai-literacy, epistemic-debt, code-ownership, debugging, anthropic-track, local-first]
related:
  - "[[Ledger — 24-Hour Solo Build Plan]]"
  - "[[UC Berkeley AI Hackathon]]"
  - "[[CareOps]]"
  - "[[Berkeley AI Hackathon Sponsors]]"
---

# Ledger

> *"You can outsource your thinking, but you cannot outsource your understanding."* — Andrej Karpathy

> **Canonical spec — committed direction (2026-06-19).** This is the single source of truth for what Ledger *is* and what gets demoed. The hour-by-hour build lives in **[[Ledger — 24-Hour Solo Build Plan]]**. The design-evolution trail (v1 recurrence vision, the code-ownership-audit pivot, the grill-centric pitch, the Debug-to-Own swap, the full product-experience spec) is archived under `_archive/` — folded in here, kept browsable there.

## The thesis in one line

> *"Claude Code makes developers faster. Ledger makes sure they still own what they ship."*

Pro-responsible-use, not anti-Claude — the register Anthropic rewards. The sticky phrase: **"fragile expert"** — someone who can ship with Claude but can't maintain without it. (Detach "fragile expert" from "junior"; demoing on yourself makes the framing more credible — even a capable engineer accumulates this.)

**Sharpest product claim (use verbatim):** *"Ledger finds load-bearing code decisions with no evidence of ownership, then makes you prove you can still operate them — by breaking one and asking you to fix it."*

## The villain — silent epistemic debt

AI makes outsourcing understanding frictionless: you ship working code without ever building the model of it in your head. The debt is invisible precisely because each individual lookup felt efficient. The most safety-critical form is **debugging** — the skill you most need to supervise unreliable AI is the first to erode when the AI does the work.

The frame is not "a memory tool" (commodity, incumbent-owned) but **"the thing that catches you letting the AI think for you."** Memory/extraction stays below the waterline; *"do you own what you ship"* is the headline.

## What Ledger is — a finite-attention allocator

Owen already has **`/ensure-understanding`** — a Claude Code skill that runs the full diagnose→close→confirm ownership loop on an artifact you hand it. It targets the same villain. **So the verifier was never the differentiator.** What the skill *structurally cannot do* is what Ledger is:

- **It's pull, point-in-time, artifact-scoped.** You bring it the thing. It can't tell you *which* decisions across your whole repo deserve a check — the ones you don't know you don't know. **Ledger does the selection.**
- **It's stateless.** No homework, no tracking decay across PRs. **Ledger is the memory.**

**The product, precisely: Ledger allocates a finite understanding budget.** Nobody can deeply own their entire codebase; checking evenly is waste. Ledger keeps a running, decaying ledger of where ownership is thin *on the things that matter*, and surfaces the highest-leverage gaps in priority order. The output is a **prioritized, decaying worklist**, not an even audit.

**Ranking is the core IP (not detection).** Rank at display time, because priority depends on current work. First gate out trivia, stale topics, and candidates without a credible exercise; then prioritize: **previous struggle + code changed** → **unchecked + relevant to the current path** → **high-risk + weak trail** → **time-based revisit** → background backlog. Within a tier, use centrality / blast-radius, risk-class (auth, persistence, migrations, anything irreversible), reasoning-trail strength, prior attempts / coach use, and exercise quality. The strongest signal is **relevance to what you're about to touch (just-in-time):** a `SessionStart` hook reads `cwd`/branch and surfaces debt *on the path you're entering*.

**Never ask the user to trust an opaque score.** The card must state why the topic is ranked now: *"You're entering this path; this isolation decision has never been practiced; no rationale was found."* Avoid an aggregate ownership score in both the ranker and the UI.

**The "right twice" risk (carry it honestly).** You have to be right twice: find real gaps *and* order them well. Trust in the queue dies on first use if the top item is trivial or already-owned. Detection is the validation gate; ranking is product judgment, iterated.

## The concept unit — load-bearing decision point → topic

**Unit:** a deterministically-extractable code artifact that **encodes a choice** a future maintainer needs the *why* of to change the system safely. The unit is really the **maintenance obligation**; the artifact is just where it shows up.

**The flag:** `load-bearing decision × weak reasoning trail (absent from ADRs + CONTEXT + comments + PR/commit messages)`.

**The crucial refinement (learned the hard way):** "load-bearing" must mean **a defendable *decision*, not a high-fan-in *symbol*.** An early build ranked by raw fan-in and surfaced `get`/`set`/`encode`/`render` — common, not decision-weighted. Bias extraction toward: non-obvious constants/thresholds, algorithmic function bodies (branching/math/ordering), chosen dependencies, control-flow ordering, auth/access logic — and **drop generic helpers.** Self-validating filter: if you can't form a coherent "defend this decision" question, it's trivia → auto-cut.

**The durable unit is a *topic*, not a function or mutation.** A topic describes the maintenance obligation ("Tenant isolation in document caching") and survives renames and implementation changes. A *check* is one point-in-time exercise against a particular code snapshot. The model:

```
Project
  → Topic
    → Code and conversation evidence
    → Ownership checks
      → Attempts
      → Reflection
    → Revisions as the code changes
```

**Vocabulary:** a **decision anchor** is the concrete code artifact (threshold, branch, dependency, access check); a **topic** is the durable, repository-specific maintenance obligation; a **concept** is a later generalized learning pattern supported by multiple topics (for example, *isolation boundaries*). Topics belong in the core ownership ledger. Concepts are a derived learning view and must remain linked to their source topics.

### Grounded extraction and revision flow

```text
All Git commits + code/tests/docs + Claude receipts
  → immutable evidence records
  → deterministic decision-anchor extraction
  → bounded LLM labeling (never free-scan / sole-detect)
  → create, revise, merge, split, supersede, retire, or reject topic
  → context-sensitive ranking
  → Debug-to-Own check
  → attempts + coach use + reflection
  → ownership event
  → future commit / relevance / time trigger → repeat
```

**Ingest every commit in an enrolled repository, not only "Claude commits."** Git is the reality stream; Claude sessions are a separate provenance stream. A human commit can invalidate a tracked decision, and Claude attribution is inherently fuzzy because Claude edits files while the user usually creates the commit. A fast `post-commit` hook records local changes; `SessionStart` reconciles stored HEAD against current HEAD to catch pulls, rebases, rewritten history, and missed hooks. Always check changed files against tracked anchors; reserve broader extraction for Claude-touched files, high-risk paths, and scheduled scans.

For each deterministic candidate, construct an evidence bundle: exact code snapshot (commit + blob + path + symbol/span), callers/tests/risk signals, docs/comments/ADR/commit-message search, and related Claude receipts. The LLM labels only this bounded bundle: the encoded choice, maintenance obligation, invariant, failure mode, load-bearing rationale, trivia verdict, and possible narrow exercise. Every output cites evidence IDs; the LLM never invents a topic from conversation alone.

**Topic identity is stable; revisions are immutable.** A rename may keep the same topic. An implementation rewrite with the same invariant creates a new revision. A materially different obligation may split or supersede the topic. Removal retires it without deleting history. Checks and reflections remain attached to the exact revision practiced; evidence never silently transfers to materially changed code.

## The verifier — Debug-to-Own (break it, make them fix it)

**The committed mechanic.** Instead of *asking* you to defend a decision (the grill — now demoted, see Roadmap), Ledger takes the actually-committed code for a flagged decision, **injects a small semantic defect targeted at that decision**, spins up a sandbox where the defect is observable (a failing test), and makes the owner diagnose and repair it.

Why this won over the grill:
1. **It's the most direct operationalization of the study.** The Anthropic RCT's largest gap was debugging, and the control group built skill *by encountering and resolving errors independently*. A seeded-bug-fix reruns that learning event on demand.
2. **It heals the wound that killed validation.** The grill needs an LLM judge to grade "did they really understand" — fuzzy, the same thing that failed Gate B. A bug-fix has ground truth: does behavior match the known-good pre-mutation original?
3. **It's unbullshittable.** You can talk past "defend this decision" with a fluent rationale (illusion of explanatory depth). You cannot talk past a failing test.

**Prior art (so we don't claim to invent it):** the mechanic = **mutation testing + "bebugging"** (DeMillo/Lipton 1978; PIT, `mutmut`, `cosmic-ray`, Stryker; Meta now LLM-generates mutants). The twist: the detector is a **human**, not a test suite, and the target is *your own committed code*. Mutation generation is a solved, libraried problem — **reuse mutation operators, don't invent them.**

### What the 2026-06-19 spike corrected (load-bearing)

A throwaway run (four decision-targeted mutants on a real Claude-authored token-bucket rate limiter, fixed blind in a temp-dir sandbox; full log in the prototype's `SPIKE_PLAN.md`) found:

- **The mechanic works — feasibility PASS.** All four mutants were generatable from a substring spec, non-equivalent (each broke ≥1 green test), and observable (fixed from the RED suite, no diff shown). The "break it, sandbox it, fix it" beat is real and demoable.
- **"Fix-success proves ownership" did NOT hold — grade on struggle, not solve.** The owner solved 4/4; green is necessary, not sufficient. The signal is the *cost* of getting there — **time / attempts / hesitation**, never the binary solve.
- **Time was confounded with mutant blast radius** (1 broken test → ~60–90s; 9 broken tests → ~2240s). A wide-blast mutant measures debugging-*localization*, not decision-*ownership*. → **Mutants must fail narrowly and implicate the targeted decision's behavior;** control blast radius or you measure the wrong skill.
- **Owning a concept ≠ spotting a plausible mutant of it.** A subtle operator swap is a visual-search problem, not a knowledge one. → keep a rationale check in reserve (this is part of why the grill survives as a roadmap "why" prong).

**Net:** build the verifier (de-risked), but make its verdict **struggle-graded** and its mutants **blast-controlled** — and don't pitch "fix-success proves ownership."

### Where the LLM sits

Deterministic extraction *detects* candidates; the **LLM proposes labels** ("what decision does this encode? load-bearing or trivia?") and **proposes the mutant** (which line to break, how). It is never the sole detector or ranker, and it never decides pass/fail — explicit evidence gates and the test do. Treat mutant generation as a **quality-gated** step (sanity-check it actually changes behavior and isn't equivalent), not a fire-and-forget call.

## The coach's boundary

The coach is core because the study's strongest result is not "avoid AI" — it's "use AI for conceptual inquiry rather than cognitive offloading." Three allowed response types:

1. Explain a general concept.
2. Ask a diagnostic question.
3. Suggest an observation or experiment.

> **User:** *Just tell me what I need to change.*
> **Coach:** *I can't provide the patch. First identify every value that determines whether two cached results may safely be shared. Which of those currently participates in cache identity?*

**The best defense against leaking the answer is not the system prompt — it's withholding the answer from the model.** Architecturally, the coach must **not** receive: the original unmutated implementation, the mutation diff, the intended patch, or the target line. Give it only the sandbox, failure evidence, and topic description. For the demo, constrain responses to structured fields (`Concept` / `Diagnostic question` / `Suggested observation`) and **reject code blocks/patches in the response layer.**

**The coach runs on the user's own Claude Code CLI, not the Anthropic API** (headless `claude -p`, coach policy via `--append-system-prompt`, all tools denied). Two payoffs: (1) **adoptability** — no API key to manage, no per-token cost; it rides the user's existing Claude Code auth and their chosen model; and (2) **withholding becomes an enforced permission boundary** — with Read/Bash denied, the coach *cannot* open the sandbox files or original code even if it tried, not just "we didn't put it in the prompt." It also makes Ledger **Claude-Code-native on both halves** — hooks for ingestion, the CLI for coaching.

## Product surface — persistent local app, not a CLI interrogation

- **Hooks + CLI:** invisible capture and lightweight notifications. Hooks are Ledger's *sensory system*, not its interface.
- **Local web application:** the primary product surface.
- **Sandbox:** an embedded ownership exercise over code the developer shipped.
- **Persistent store (SQLite):** topics + evidence retained across sessions and code changes.

### Install & passive operation

```text
$ ledger install
✓ Created ~/.ledger/ledger.db
✓ Installed Claude Code hooks
✓ Installed git commit hook
✓ Ledger running at http://127.0.0.1:4317
```

Hooks are global; Ledger discovers repos when sessions occur inside them. If the server is stopped, hooks write to a local spool and exit fast — **they must never block Claude Code or git.** At session start, one quiet line:

```text
Ledger: 2 checks ready for docs-api · Open http://localhost:4317/p/docs-api
```

**Do not block commits or merges by default.** The study supports timely comprehension checkpoints, but an unvalidated hard gate makes developers uninstall. Strict gating is an optional policy later. Treat repos as projects but **don't make GitHub the identity** — local-first, supports repos without remotes.

Avoid an unsupported aggregate "ownership score." Show observable states: *Check recommended · In progress · Practiced · Code changed since practice · Revisit suggested.*

### The ownership-check workspace

Opening a check feels like a small local coding environment: a **Task** pane (the current behavioral failure), a **Sandbox** pane (small file tree + embedded editor, likely Monaco + a **Run checks** button + test output), and a **Coach** pane. A server-side temporary-directory sandbox runs the real test. **Do not build an arbitrary interactive terminal** (PTY streaming, process management, security — no hero-demo value).

### Completing a check

After behavior is restored, three reflection prompts (not LLM-graded exam answers):
1. What invariant did you restore?
2. Why does that invariant exist?
3. What future change could violate it again?

Recorded history per topic: behavior restored (yes/no), elapsed, check runs, conceptual help used, **direct solution given (no)**, reflection captured, code snapshot. This combines the study's three useful mechanisms — encounter-and-resolve-an-error, ask-conceptual-questions, explain-after-generation — without claiming one challenge proves ownership.

### Updating understanding without inventing a score

Treat "understanding" as a **revision-specific evidence profile**, not a scalar. Record operational practice (behavior restored, elapsed, attempts), independence evidence (coach use; direct solution withheld), rationale evidence (reflection captured, not LLM-graded), and freshness (the practiced commit still matches current code or does not). Visible states remain observable: *Check recommended → In progress → Practiced → Code changed since practice → Revisit suggested*.

Green is necessary but never means "mastered." Completion adds an ownership event and a cooldown; significant struggle can shorten the next revisit. Time alone may suggest a revisit but must not assert decay. A later real change made successfully without solution-providing assistance can become weak independence evidence, not proof.

### Persistence model — immutable evidence, versioned interpretation, derived state

SQLite is an append-oriented ownership ledger, not a mutable topic JSON blob. The logical tables are:

```text
projects           local Git identity (`git_common_dir`), display metadata
commits            SHA, parent, timestamp, project
sessions           Claude session ID, timestamps, source hash
topics             stable ID, canonical maintenance obligation, lifecycle state
topic_revisions    topic ID, revision, commit, invariant, risk, fingerprint
evidence           code / conversation / docs / commit / test source records
revision_evidence  evidence role, confidence, link method
trail_scans        what docs/comments/ADRs/messages were searched at which commit
topic_events       created / practiced / code-changed / revisit / superseded / retired
checks             exact topic revision + sandbox/mutation/test metadata
attempts           elapsed, runs, results, coach-use observations
reflections        user-authored invariant / rationale / future-risk answers
```

Code evidence stores commit SHA, Git blob SHA, repository-relative path, symbol or normalized AST fingerprint, display span, captured excerpt, and excerpt hash. Commit/blob identify immutable code; path and line number are navigation hints. Conversation evidence stores the normalized excerpt/tool sequence, session ID, timestamps, touched files, source-event hash, and link confidence before the raw JSONL expires. LLM proposals retain model/prompt/schema version and their input evidence IDs so promotion into a topic revision is auditable.

### Compounding intelligence and personalization

Each cycle improves four separate models without weakening source grounding:

- **Repository intelligence:** stable topic identities, code↔topic mappings, refactor lineage, historical invariants, risk patterns, and reasoning-trail coverage reduce duplicate/trivial extraction.
- **Ranking personalization:** opens/ignores, explicit dismissals (`trivia`, `already understood`, `wrong scope`, `obsolete`), exercise struggle, coach use, and preferred revisit cadence tune what appears first. These signals change priority, never source facts.
- **Exercise calibration:** baseline-green / mutant-red validation, failure blast radius, attempts, elapsed time, and observed ambiguity identify mutations that are too broad, obvious, equivalent, or poorly localized. Compare struggle only across difficulty-matched exercises.
- **Cross-topic learning:** repeated grounded topics can support a generalized concept (for example, tenant caching + organization jobs + auth propagation → *isolation boundaries*). The concept always retains links to the source topics; it never becomes free-floating LLM memory.

The flywheel is: **more development → richer grounded topic history → better selection → better-matched exercises → stronger ownership evidence → more personalized future ranking.** User corrections and immutable evidence remain the guardrails at every pass.

## Provenance model — code is truth, docs are the trail, transcript is the receipt

The signal lives in the **join** of three sources:
- **Code** = ground truth — what entered the system; the thing you exercise. *(Validation depends on this.)*
- **Docs / ADRs / CONTEXT / comments** = the reasoning trail — whether the *why* was captured; the "weak trail" half. *(Validation depends on this.)*
- **Transcript** = the receipt — whether Claude was involved. *(Validation does NOT depend on this.)*

Every topic card must answer five inspectable questions: **what exists** (exact code/commit), **why it matters** (risk/invariant/blast radius), **where it came from** (conversation receipt when available), **what reasoning is missing** (a persisted trail-scan receipt, not a naked claim), and **why now** (the ranker's current trigger). Conversation is optional supporting evidence; no active topic exists without exact code grounding.

**Keep the transcript out of validation, on purpose:** diff↔session linking is fuzzy (Claude Code gives `cwd` + timestamps + which *file* was touched, not "this decision was made here"), and "engagement: low/med/high" is exactly the signal that failed Gate B. Store links as `exact`, `heuristic`, or `hand_verified`; say *"related session"* rather than imply causality when uncertain. **But provenance is a strong demo asset:** build **one hand-verified real evidence chain** (actual code + a real transcript snippet where Claude edited that file + the genuinely-missing ADR). *"The core signal is proven without needing to guess what Claude did; provenance is what makes it Claude-Code-native."* **Do not build the automated diff↔session linker** — off the critical path, fuzzy, unneeded for the demo.

## The artifact card (the product in one screen)

Three panes, each grounded in something real:
1. **Code reality** — the actual load-bearing decision, with *why it's load-bearing* ("on the retrieval path, called by 5 files").
2. **Claude receipt** — a real transcript snippet + tool-call provenance (`Read rerank.py → Edit rerank.py → Bash pytest`). The Claude-Code-native beat Anthropic appreciates.
3. **Missing reasoning** — what Ledger searched (ADRs, CONTEXT, README, commit msg) and didn't find. The moment the flag feels grounded, not preachy.

The core UI move: **"Ownership check recommended," never "you don't understand."** Infer *"this deserves a check"* from silence — modest, professional, hard to argue with. Only the **check result** turns a candidate into confirmed debt; Ledger never asserts the gap, it *tests* for it.

## Demo sequence (~3 min, the committed flow)

- **0:00–0:20 — Problem.** *"AI lets me ship code I haven't built the debugging instincts to maintain. Anthropic found the largest skill gap is debugging — not code generation."*
- **0:20–0:35 — Passive notification.** Start Claude Code in a prepared repo; the `SessionStart` hook prints one quiet line: *"Before you touch this path — 2 load-bearing decisions here you've never owned, ranked."* (selection + just-in-time — the differentiator, up front.)
- **0:35–1:05 — Dashboard.** Open Ledger; show several descriptive topics and *why the top one was selected*. Open the tenant-isolation topic; show its code + conversation grounding (the three-pane card).
- **1:05–1:25 — Start the check.** Ledger creates a local sandbox, applies the curated mutation, validates that exactly one behavioral check fails, opens the exercise.
- **1:25–1:55 — Use the coach.** Ask directly for the solution; the coach refuses the patch, explains how caching can bypass DB isolation, asks a diagnostic question. (Deliberate resistance to cognitive offloading.)
- **1:55–2:25 — Repair.** Inspect, repair, rerun checks → green.
- **2:25–2:45 — Reflection & persistence.** Answer one invariant question; return to the topic page; show recorded practice history.
- **2:45–3:00 — Vision.** Show (don't implement) a small Learning preview ("Emerging pattern: isolation boundaries → related topics"). Narrate that Ledger revises topics as code changes and eventually derives cross-project learning plans.

**The climax must be a real, pre-found struggle** — a topic where the cost of getting to green is genuinely visible — not improv on stage. You can't show "tracked over weeks" in 3 minutes: *narrate* the longitudinal/decay story, *show* the worklist + just-in-time surface + one **seeded-but-real** memory beat ("owned last month, code changed, re-surfaced"). **Disclose curated components as curated.**

## Pitch & positioning (judge-facing)

**Anthropic-track framing — operationalize their own conclusion.** Frame as a **Claude Code learning/safety layer.** Headline:

> *"Anthropic's own RCT found developers who offload to the AI score two letter grades lower — worst of all on debugging. Ledger operationalizes that: it catches which side of the line your shipped code falls on, and makes you earn the understanding back."*

**Concede the tutor, win on the audit.** Claude already teaches (Learning Mode / `/output-style Learning`). Ledger isn't a better Socratic prompt — it's the **selection + retention + verification** layer: *what* gets tested, *when* it's retested, whether your future behavior shows independence. *"Claude can teach; Ledger checks whether the teaching stuck."*

**"Isn't this just `git show` / code review?"**
> *"`git show` tells me what I changed. It can't tell me what I shipped that I can't actually explain — and if I could see that gap by reading the diff, I wouldn't have shipped it."*

Three things a diff structurally can't do: **select** the load-bearing-unexplained slice · **compare** code against the reasoning trail · **adversarially verify** (break it and make you fix it, vs. self-review where the illusion of understanding lives). Pre-load the follow-up ("isn't this disciplined code review?"): yes — Ledger is the disciplined dev who writes ADRs and reviews every line, *automated and made adversarial*; almost nobody does it, the ones who do can't self-grade past the illusion, and AI multiplies shipped-but-never-reasoned surface faster than any review habit scales. Claim git/review *doesn't surface debt in practice*, not that it *can't*.

**Vs. Claude's built-in memory — same plumbing, opposite purpose.** Claude's memory succeeds when you depend on it *more*; Ledger succeeds when you need it *less* (verify-by-absence). A feature that wins by getting you to use the AI less is at war with the business it lives in — that incentive misalignment is the moat. *"Same data, opposite goals."* Concede the mechanism; win on posture.

**README/adoption language ≠ pitch language.** Don't sell it as *"a tool that judges your understanding"* (devs uninstall that). Sell: *"A local Claude Code companion that keeps a repo-level ownership ledger for AI-assisted code — it catches risky code you shipped but can't safely change yet."* Same product, two registers.

### Sponsor prizes — keep in mind

**Anthropic remains the natural primary.** Keep these additional sponsor prizes in mind, but only integrate them when they strengthen the working spine rather than becoming hour-22 bolt-ons:

- **Redis:** possible store/cache for topic retrieval, code-context embeddings, or ranked-worklist lookup. Use only if it replaces real plumbing; SQLite remains the frozen demo persistence layer.
- **Sentry:** natural instrumentation for failures across hook ingestion, sandbox creation, test execution, coach calls, and the web app. Strongest low-risk addition once the end-to-end check works.
- **Arize:** trace and evaluate topic labeling, ranking explanations, mutant quality, and coach behavior. Strong fit for a small golden set proving the AI components improved, but automatic extraction/eval remains off the critical path.

Decision rule: **functional Ledger loop first; sponsor integration second; no architecture changes solely for prize coverage.**

### Candidate types that demo well

Algorithmic function (retrieval/rerank/chunking), a behavior-controlling config knob, a core-path dependency, auth/access logic, retry/cache behavior. **Avoid** tiny utilities, generic helpers, obvious imports, formatting commits — they make the flag feel like trivia (the failure mode the whole design corrects).

## Evidence — Anthropic's own research (verified; use verbatim, don't paraphrase)

> **Source:** *"How AI assistance impacts the formation of coding skills"* — Anthropic Research, **published 2026-01-29**. https://www.anthropic.com/research/AI-assistance-coding-skills (verified on-page 2026-06-17). Cite the **Anthropic page directly**, not aggregators (InfoQ/Medium garble the numbers).

- **Design:** RCT, **52 mostly-junior engineers**; learned the Python **Trio** async library, coded two features, took a comprehension quiz.
- **Headline:** AI-assisted group **50%** vs **67%** for hand-coders — roughly **two letter grades** (Cohen's *d* = 0.738, *p* = 0.01). Phrase as *"~17 **points** lower"* / *"two letter grades"* — **never** "17% fewer skills." (Full-PDF figures: 17% / 2 grade points, d = 0.738, p = 0.01, debugging = largest sub-area gap.)
- **Biggest gap = debugging** — *"the ability to understand when code is incorrect and why it fails."* (Debugging = maintenance ownership; the most on-point finding, and exactly what Debug-to-Own exercises.)
- **Their explanatory axis is Ledger's:** low scorers (<40%) **delegated generation / used AI as a debugging crutch** — *"they offload their thinking to AI"*; high scorers (≥65%) **asked conceptual questions** / did generation-then-comprehension.
- **Quotable:** *"AI-enhanced productivity is not a shortcut to competence"*; AI assistance *"should enable humans to work more efficiently **and** develop new skills."*

**Rigor guardrail — cite for the *problem*, never as proof the *detector* works.** Anthropic had ground truth (controlled task + quiz); you can't recover that from passive logs (which is *why* engagement classification failed Gate B). Ledger's sandbox check **is** the quiz, applied to real shipped code. Hold that distinction if probed.

**Adjacent confirmed facts:** Claude for Education / Learning Mode is real (launched Apr 2025; Socratic; all users Aug 2025); Claude Code has `/output-style Learning` (+ "Explanatory"). Name the `/output-style Learning` detail to show homework. (For color, *not* Anthropic: MIT Media Lab "Your Brain on ChatGPT"; Microsoft–CMU on critical thinking.)

### Research → feature crosswalk (Q&A prep)

> Ledger operationalizes the RCT's behavioral findings beat-for-beat. **One-liner:** the study found *Conceptual Inquiry* scored highest but developers abandon it under deadline (the *Progressive AI Reliance* slide); **the coach removes the choice — conceptual help is the only channel open, so the best-observed behavior becomes the default instead of a discipline.** Lead with Anthropic; the broader literature is corroborating color only (per the rigor guardrail above).

| Study recommendation | Ledger feature that operationalizes it |
|---|---|
| Conceptual Inquiry scored highest + fastest | Coach answers *only* concept/goal/diagnostic/observation; patch architecturally withheld (coach gets no code) |
| Generation-then-comprehension (the missing step) | Ledger *is* the comprehension step, applied retroactively to shipped, generated code |
| Don't let AI rob you of errors; debugging builds skill | Debug-to-Own re-manufactures the exact error the AI spared you; coach won't return the fix |
| Attempt-first; AI-as-reviser, not originator | The check forces your diagnosis/fix first; coach guides, never originates |
| Metacognitive mirror / reflect-after / explain-it-back | The check forces you to articulate the fix; the coach's diagnostic questions mirror your reasoning back |
| Sustain engagement; watch the delegation slide | Decaying ledger + verify-by-absence catch drift across PRs over time |
| Learning modes good; agentic tools riskier | Ledger rides the agentic Claude Code workflow the paper flags as highest-risk; concedes the tutor, wins on selection + verification |

Secondary sources (color, **not** the anchor — don't over-cite to judges): "I'm Not Reading All of That" (cognitive engagement with agentic assistants), Cognitive Mirror / metacognition (Frontiers), "metacognitive laziness" (Auckland), Plan-More-Debug-Less, AI-as-reviser-not-originator findings.

## Validation status

- **Experiment 1 (transcript-engagement): DONE → FAILED Gate B.** An LLM couldn't recover *engaged vs. deferred* reliably even from full transcripts; recurrence clusters on phrasing, not content. Do not build on it. (Prototype `RESULTS.md` / `ADR-0002`.) This killed the v1 recurrence→Socratic direction and forced the code-ownership pivot.
- **Experiment 2 (silent-debt / code-ownership): LIVE.** First pass surfaced symbol-recall trivia → corrected to load-bearing *decisions* + the Debug-to-Own sandbox verifier.

**The core unvalidated assumption (carry honestly):** *"load-bearing × no reasoning trail → debt"* has a **flooding problem** — absence of a trail is the default state of almost all code, so importance-ranking is the only thing holding it back, and it's not yet proven that `(important × untrailed)` separates "can't explain it" from "owns it fine but never documented it."

**The clean discrimination instrument is now a post-event asset** (the Debug-to-Own swap makes it deterministic): seed a *matched, difficulty-matched, blast-controlled* mutant in a Flagged decision (load-bearing ∧ untrailed) and a Control (load-bearing ∧ trailed); measure **time-to-fix / attempts / struggle** (not solve), multiple subjects, aged comprehension. No LLM judge. **The event is June 20–21 — this is a reason the concept is sound, not a thing to run before building.** Don't relapse into validation-first.

## Guardrails

- **Don't become a linter.** Ledger tests the **person**, never grades the code. Output is *"you may not be able to maintain this,"* never *"this code is undocumented/suboptimal."* The moment it grades the code, it's `sqlfluff`, not Ledger.
- **Ledger recommends checks; it does not assert that a developer lacks understanding.**
- **Green behavior is necessary but does not prove ownership** — record struggle and reflection without inventing a universal score.
- **Local-first; hooks must never block normal development.**
- **Curated demo components must be disclosed as curated.**
- **Match the artifact class to the pilot codebase.** The pilot is a RAG/retrieval system (object store + vector store + rerankers) with a thin relational schema → pilot on **config/env knobs + high-centrality retrieval/rerank functions**, not DB columns.
- **Keep the ledger live (the one point from the inbox draft):** new code can revert old decisions, so a tracked decision that gets modified again — still untrailed, previously fumbled — goes to the top of the queue. The `code-changed` re-surface trigger is what keeps the ledger relevant rather than a stale one-time scan.

## Scope — solo definition of done

The convincing vertical slice (full hour-by-hour plan in **[[Ledger — 24-Hour Solo Build Plan]]**):

1. Claude and Git hooks record activity for **one real repository**.
2. The local web app shows that one project + several seeded ownership topics.
3. One topic is grounded in real code, commit, and session evidence.
4. Starting its check creates a real temporary sandbox with a curated mutation.
5. The browser lets the user edit one file and run a real test.
6. The coach answers conceptual questions without producing a patch.
7. Attempts, elapsed time, reflection, and completion persist in SQLite.
8. The topic page updates after completion.

**Use exactly one real Git project in the demo.** Give it 3–5 ranked topics, one fully grounded hero topic/check, and optionally one previously practiced topic to demonstrate persistence. Multiple real repositories add hook, reset, and provenance risk without proving another product capability. If sample projects appear visually, label them explicitly; one credible project is better than several suspicious ones.

## Roadmap / narrate-only (don't build for Saturday)

- **The grill, as the "rationale" prong.** Debug-to-Own carries "can you operate it" (deterministic). The grill — *"why this approach over the alternatives"* — is the *rationale* prong a bug-fix can't reach, and `/ensure-understanding` already implements it. **Demoted to narration**, not built into the hackathon flow; it's the portfolio's second verifier, not the live one.
- **Longitudinal / decay / verify-by-absence** — the over-time moat: did your dependence on the AI for this *actually drop* in later real work. The sandbox check is the point-in-time verifier; verify-by-absence is the over-time one. Narrate; show one seeded-but-real memory beat.
- **LLM-generated mutants (Meta-style) + ephemeral per-commit sandboxes** — the same trap class as the provenance linker; narrate, don't build.
- **Automatic topic/mutant generation, arbitrary-repo sandboxing, cross-project learning plans, calibrated ownership scoring** — vision slides.
- **Spaced-repetition export (Anki/AnkiConnect)** for the conceptual-recall slice — *describe* as productization; **do not integrate live** (invisible plumbing + forces a judge to have Anki installed). Build the in-context loop yourself.
- **Broad provider-agnostic** (Cursor/Copilot/ChatGPT/Gemini) stays the TAM/north-star slide, and **Coach/nudge parity across providers stays roadmap.** _Exception, pulled into Saturday scope (a Codex-native partner joined):_ two-provider **ingestion** (Claude Code + Codex) via a `ProviderAdapter` interface + provider-labeled provenance, cheap to build/test on the partner's own real sessions. The Codex adapter is the vision-beat proof the abstraction is real; the **spine stays Claude-Code-native** — hero loop, `SessionStart` nudge, and Coach run on Claude only (the only zero-friction `SessionStart`+local-JSONL path; Codex has no `--disallowedTools` equivalent for the withholding Coach). "Support both providers" = **ingestion parity + provider-labeled provenance, not Coach/nudge parity.** Gated on an hour-0 Codex spike; see `docs/adr/0001-dual-provider-ingestion-claude-native-spine.md` and Log 2026-06-20.

## Design rationale carried over (don't re-derive)

- **Engine vs. product.** Memory/extraction below the waterline; "do you own what you ship" is the headline. Never reframe around "personal memory system" (crowded, incumbent-owned).
- **Karpathy friction↔fidelity tension.** Understanding is the residue of in-the-moment struggle — which argues *for* the high-friction in-the-moment intervention (the sandbox fix *is* this) and against a passive dashboard. Ledger *manages* the problem (makes invisible debt visible + forces partial real struggle + measures independence); it does **not** *solve* it. Never pitch it as "solving" Karpathy.
- **Data substrate (verified on-machine 2026-06-15).** Local transcripts exist only for **Claude Code the CLI** (`~/.claude/projects/**/*.jsonl`, full prompt+response+tools; Owen had 797 files) — claude.ai/Desktop/API are server-side. There's a **~30-day default purge** (`cleanupPeriodDays`) → the raw feed self-destructs, so **Ledger's own store is the durable layer** and the hook only captures forward from install. *Bump `cleanupPeriodDays` on the demo machine before Saturday* so demo material isn't shredded. (The same "do local logs with tool-call granularity exist on-machine?" test gates the **Codex** adapter — ADR-0001 hour-0 spike, check (a) — before its provenance is trusted.)
- **Honest company-vs-hackathon verdict.** Strongest hackathon candidate raised (real-if-partly-commodity moat, genuine conviction, meta hook, clean Anthropic fit, runs on Owen's own real data). As a company it's shakier — it *sells friction* into a market that adopts AI *because* it's frictionless. For a hackathon the friction is a strength (sharp POV); as a business it's the headwind. Unlike Curio/CareOps, the weakness is *adoption*, not *demo*.

## Log

> Dated entries, newest on top. (Pre-2026-06-19 detail lives in the archived design notes under `_archive/`.)

### 2026-06-20 (partner joined → dual-provider ingestion, Claude-native spine)
A second, **Codex-native** engineer joined. Recorded in **ADR-0001**: pull a `ProviderAdapter` ingestion interface forward to day 1 with **two adapters** (Owen = Claude `~/.claude/projects/**/*.jsonl`; partner = Codex), **provider-labeled provenance** in the UI. The **spine stays Claude-native** — hero loop, `SessionStart` nudge, and Coach (`claude -p`, all tools denied); a multi-model coach stays roadmap because Codex exposes no `--disallowedTools` equivalent and the raw-API escape reintroduces the key/per-token cost the design killed. Codex ingestion + Codex nudge are **gated on an hour-0 feasibility spike** (does Codex persist local logs with tool-call granularity? does it expose a session-start hook?), mirroring the on-machine Claude-substrate check (2026-06-15 above). This **partially supersedes the "provider-agnostic = roadmap-only" bullet**: broad provider-agnostic stays north-star, but *ingestion* for two providers is now in scope. Work split into **vertical slices by provider**; tracked as GitHub issues in `owenarnst/ledger`. Same session: the **Receipt** (the provider-labeled provenance view; defined in `CONTEXT.md`) got disclosure **L1 + L2 committed, L3 raw-log as a stretch**, and the **Missing reasoning** card was **cut** (it required computing an *absence*, which can't be grounded honestly). _Still open: the "solo definition of done" framing below predates the partner — a separate reconciliation._

### 2026-06-19 (grounded longitudinal data model)
Locked the end-to-end ownership loop: ingest **all Git commits** as code reality and Claude transcripts separately as provenance; deterministically extract decision anchors; create immutable evidence-backed topic revisions; rank at display time with visible reasons; attach Debug-to-Own attempts/reflections to the exact revision; update an observable evidence profile rather than an ownership score; and re-surface on code change, current relevance, prior struggle, or time. The demo uses **one real Git project** with several topics and one hand-verified code↔conversation↔missing-trail chain. Long-term concepts are derived across grounded topics, never free-floating LLM memory.

### 2026-06-19 (tech stack frozen)
Pre-event stack grill (recorded in **[[Ledger — 24-Hour Solo Build Plan]]** → Frozen tech stack). Spine = **Python-first monolith**: FastAPI backend + React/Vite frontend + a Python hero repo built with Claude Code **at hour 0, in-window** (corrected 2026-06-19 from "pre-event," which conflicts with the started-during-the-event rule, `03_hacker_guide.md:81`; building in-window yields identical real transcripts, so it costs ~1h, not authenticity; not Omnibay code). Sandbox = temp-dir + `subprocess` + **exit-code-as-oracle**, one Python/pytest adapter, env pre-baked, no containers (the cross-language story is a thin per-language adapter + dependency-provisioning, deferred). Monaco editor (textarea fallback). The riskiest pieces (sandbox loop, hooks) were de-risked in the throwaway prototype's `derisk/`. **Biggest decision: the coach runs on the user's own Claude Code CLI** (`claude -p`, all tools denied), not the Anthropic API — no API key, no per-token cost, and withholding-the-answer becomes an enforced permission boundary. Ledger's only Claude dependency is the Claude Code CLI itself.

### 2026-06-19 (consolidated to canonical spec)
Committed to the **sandbox/coach (Debug-to-Own) version** as canonical. Six Ledger docs collapsed to two: this spec + **[[Ledger — 24-Hour Solo Build Plan]]**. The four intermediate design notes (Code Ownership Audit, Demo & Pitch, Debug-to-Own, Product Experience) and the v1 vision note archived under `_archive/`. The **grill is demoted to a roadmap "rationale" prong**; the live verifier is break-it-in-a-sandbox-and-fix-it, **struggle-graded** (not solve-graded) with **blast-controlled** mutants, per the 2026-06-19 spike.

### 2026-06-19 (Debug-to-Own spike + product-experience spec)
Spike confirmed the break-it/fix-it mechanic is feasible and demoable but that fix-*success* carries no ownership signal (grade on struggle) and mutant blast radius confounds time (control it). Product experience fleshed out into a local web app — dashboard → topic card → sandbox + coach + test runner → reflection → persistence — replacing the grill step with the coach+sandbox. Solo build plan written around it.

### 2026-06-18 (finite-attention allocator + defend-it reframe)
Sharpest differentiation vs `/ensure-understanding`: the verifier was never the differentiator — **selection + memory** is. Ledger = a finite-attention allocator producing a prioritized, decaying worklist; ranking is the core IP; `SessionStart` just-in-time is the demo spine. "Load-bearing" sharpened to *defendable decision*, not high-fan-in *symbol*. Provenance model pinned (code=truth, docs=trail, transcript=receipt; transcript stays out of validation, is a demo asset via one hand-verified chain).

### 2026-06-17 (engagement test failed → pivot to code-ownership audit)
The deciding engagement-classifier test failed Gate B. Rather than fall to CareOps, pivoted to the **silent-debt / code-ownership** signal: load-bearing code shipped with no reasoning trail. Concept unit = load-bearing decision point; architecture = deterministic extraction → LLM labels-never-detects → verifier.

### 2026-06-15 (origin + signal-validation spike)
Captured as a candidate (the first idea Owen had genuine conviction for). Memory-is-the-engine / anti-outsourcing-is-the-product line locked. Narrowed to local Claude Code transcripts for clean data + privacy. Throwaway prototype tested whether the offloading signal was real — result uncertain (delegation extractable; engagement under-determined by prompt-only data), which set up the 06-17 engagement test and its failure.

## Related notes

- [[Ledger — 24-Hour Solo Build Plan]] — the operational build (hours, checkpoints, fallbacks).
- [[UC Berkeley AI Hackathon]] — umbrella event project.
- [[CareOps]] — the fallback candidate if the ownership signal fails to hold up.
- [[Berkeley AI Hackathon Sponsors]] — sponsor map.
- `_archive/` — the superseded design notes (v1 vision, Code Ownership Audit, Demo & Pitch, Debug-to-Own, Product Experience), folded into this doc, kept for the evolution trail.
