---
type: project
status: active
owner: Owen
started: 2026-06-19
due: 2026-06-21
tags: [hackathon, ledger, ui, spec, design]
related:
  - "[[Ledger]]"
  - "[[Ledger — 24-Hour Solo Build Plan]]"
---

# Ledger — UI Spec

> Working design spec for the Ledger local web app, to feed the claude.ai design interface as a prototype/wireframe brief. Built via a `grill-with-docs` session (2026-06-19). Canonical product truth = **[[Ledger]]**; build constraints = **[[Ledger — 24-Hour Solo Build Plan]]**. This doc owns *interaction & layout*, not product thesis.

## UI glossary

> New interaction/layout terms, pinned as they resolve. Product-concept vocabulary (Topic, Check, Attempt, Reflection, load-bearing decision, flag, trailed/untrailed) is already canonical in [[Ledger]] — not redefined here.

- **Project rail** — persistent left column; the scoping chrome that nests the current project view under the global Ledger app. Expresses multi-project *capability*, not *population*.
- **Discovery hint** — quiet affordance in the rail stating the model: *"Repos appear here automatically when you run Claude Code in them."* Reframes "one project" as "one so far," not "one supported."
- **Breadcrumb scope** — `Ledger › <project>`; the app identity (Ledger, global) sits above the project scope so Ledger ≠ this repo.
- **Blast radius** — how much breaks if a decision is wrong: centrality (callers / fan-out) + risk-class (auth, persistence, migrations, irreversible). Deterministic, static. The "does it matter" ranking axis.
- **Ownership thinness** — the personal "do *you* own it" axis: decay state (`never checked → practiced → code changed since → revisit due`) boosted by AI-authorship. NOT transcript-engagement (the Gate-B-failed signal, `Ledger.md:219`).
- **AI-authorship** — a **binary provenance fact** from the receipt: did Claude author/touch this decision (`Read x → Edit x` tool-calls). A ranking signal, **not** a validation input (consistent with transcript-stays-out-of-validation, `Ledger.md:156`). _Avoid:_ "engagement" (collides with the dead classifier).

### CUT — just-in-time / "working set" (2026-06-19)
Considered ranking by relevance to *what you're about to touch* (`cwd` + branch-diff at SessionStart). **Cut by Owen:** (1) too complex for a 24h build; (2) weak in practice — he (like many devs) launches Claude Code at **repo root**, so `cwd` yields whole-repo context and the branch-diff path requires a staged feature branch. Ranking is now static **blast radius** + a personal **engagement/ownership** axis (pending — see Open decisions).
_Consequence flagged:_ the canonical spec bills just-in-time as *the* differentiator + demo spine (`Ledger.md:46, 172`). Cutting it **re-anchors the pitch on selection + memory** (`Ledger.md:37–42`, which the spec already names the real differentiator) and **drops the 0:20–0:35 JIT beat** from the demo sequence. The SessionStart hook still fires the per-repo notification (selection + memory, not JIT) — so the Claude-Code-native hooks story survives.

## Screen inventory — LOCKED (2026-06-19)

Single-project-at-a-time SPA. **Three real screens**, minimal routing:

1. **Dashboard** — the selected project's ranked Topic worklist + "why the top one was selected."
2. **Topic page** — the *artifact card* (three panes: Code reality / Claude receipt / Missing reasoning) **and** the post-check practice history are **one screen in two states**, not two screens. Pre-check: three-pane card + "Start check." Post-check: same page gains a practice-history section.
3. **Check workspace** — three panes (Task / Sandbox / Coach). The only full-bleed layout.

Folded away (not separate screens):
- **Reflection** — **CUT (2026-06-19)**, see the Reflection section. After green → persist → Topic page history directly.
- **Vision preview** (Learning preview) = a static, narrate-only panel, not a routed screen.

Demo flow: topic row → Topic page → "Start check" → Check workspace → (reflection) → back to Topic page (now with history).

## Multi-project navigation — LOCKED (2026-06-19)

**Principle: express multi-project *capability*, not *population*.** The multiplicity signal must be **passively visible** (not hidden behind a click a judge may never make).

- **Persistent left project rail** (the scoping chrome). One *real* project, selected. **No fake/seeded projects.**
- De-sparse the single-item rail with real content: the project entry + a "Tracked repos" label + the **discovery hint** as a styled footer.
- Always-on **breadcrumb scope** `Ledger › <project>` — the nesting alone says Ledger is global and repo-scoped, not single-repo.
- Honest framing: *"Ledger auto-tracks any repo you work in — here's the one I've been in,"* never *"we seeded N projects."*
- **Rejected:** aggregate cross-repo "home" with global ranking (implies cross-project ranking the product parks as vision); openable seeded secondary dashboards (fake population).

## Dashboard — LOCKED (2026-06-19)

### Ranking model
No displayed score (guardrail: no aggregate ownership score, `Ledger.md:136`). Order is computed from the factors; the UI shows the ordered list + signal chips + a plain-language "why #1," never a number.
- **Gate (to be a Topic at all):** load-bearing decision ∧ **untrailed** (weak reasoning trail).
- **Axis 1 — Blast radius** (static): centrality + risk-class. "Does it matter."
- **Axis 2 — Ownership thinness** (personal/dynamic): decay state `never checked → practiced → code changed since → revisit due`, boosted by **AI-authorship**. "Do *you* own it." Keeps Ledger from being a linter; carries the memory beat (code-changed re-surfaces to the top).

### Layout
Ranked **worklist** (ordered list of Topics), strict global rank (no sectioning — JIT removed). Each row:
- topic title (maintenance-obligation phrase);
- **state badge** (`Check recommended · In progress · Practiced · Code changed since practice · Revisit due`);
- **signal chips** — `blast radius: N callers` · `risk: <class>` · `Claude-authored`;
- **rank #1 expanded by default** into a one-sentence "why selected" naming the signals — stages the demo beat.
The memory beat rides the list: the re-surfaced topic sits near the top in `Code changed since practice → Revisit due`.

_Pitch line (recovers the Claude-native angle JIT was carrying):_ **"Ledger ranks up the load-bearing decisions Claude wrote that you never documented and have never proven you can operate."** The receipt does double duty — demo asset + ranking signal. (AI-authorship = **booster, not gate**: human-authored untrailed decisions are still Topics; Claude-authored ones rank higher.)

## Topic page (artifact card) — LOCKED (2026-06-19)

One screen, two states (per inventory). Primary target: **laptop desktop**; collapses to vertical stack on narrow/projector.

### Header
Topic title + **state badge** + framing headline **"Ownership check recommended"** (never "you don't understand," `Ledger.md:167`) + primary **"Start check"** CTA.

### Body — 2 columns (not 3 equal)
- **Left, dominant — Code reality:** the decision snippet + *why it's load-bearing* (blast-radius signals: "retrieval path · 5 callers · tenant isolation"). Code gets the width.
- **Right, stacked:**
  - **Claude receipt** (top) — real transcript snippet + tool-call provenance (`Read cache.py → Edit cache.py → Bash pytest`); AI-authorship made visible.
  - **Missing reasoning** (bottom) — what Ledger searched (ADRs, CONTEXT, README, commit msg) and didn't find. Grounded, not preachy.

### Hand-off rule
The topic page shows only grounding/why — it **never reveals the mutation or upcoming defect** (that's in the workspace; revealing it leaks the exercise). "Start check" is the hand-off.

### Post-check state (same screen)
Below the panes, a **Practice history** section appears after first completion: behavior restored (y/n) · elapsed · check runs · conceptual help used · **direct solution given: no** · code snapshot (`Ledger.md:149`). Header CTA flips "Start check" → "Practice again"; state badge updates.

### Responsive
Laptop (primary) = dominant-left + stacked-right. Narrow/projector = vertical stack (Code → Receipt → Missing). Build desktop first.

## Check workspace — LOCKED (2026-06-19)

Full-bleed, three panes. Real server-side temp-dir sandbox runs the real test; **no arbitrary interactive terminal** (`Ledger.md:140`).

### Arrangement
- **Left rail — Task:** the behavioral failure as a problem statement (what's broken + failing test name). Narrow, read-mostly.
- **Center, dominant — Sandbox:** small file tree + **Monaco editor** (textarea fallback, `build plan:67`) + **Run checks** button; **test output renders below the editor** as a read-only results panel — red/green banner + pytest output.
- **Right — Coach:** the assist pane (interaction = Q7).

### Struggle measurement — subtle (grade on struggle, not solve, `Ledger.md:86`)
Elapsed time + check-run count are **tracked**, shown **quietly** in the header (e.g. `3 runs · 4m`) — never a live stopwatch; keeps the tone non-exam.
- **Demo move:** full struggle capture is *revealed in the Topic page history* (`4 min · 3 runs · 1 concept asked · no solution given`) as proof Ledger measures ownership-*cost*, not pass/fail.

### Verdict flow
Edit buffer → Run checks → backend writes buffer to the mutated file in the temp dir → runs pytest → returns `{passed, output, elapsed}` → red banner flips green on **exit 0** (exit code is the oracle, `build plan:61`; output text is display-only, never parsed for the verdict). Plain REST, no streaming (`build plan:80`).

## Coach — LOCKED (2026-06-19)

Runs on the user's own Claude Code CLI (`claude -p`, **all tools denied**, `build plan:74`). Goal: **help the user learn without giving the answer.** Three response types → three structured fields.

### Capabilities (confirmed — Owen) — the coach must handle:
- *"What is this code supposed to do?"* → high-level **goal/intent** explanation.
- *"What is `<concept>`?"* → general concept explanation.
- *"Where do I start?"* → orientation (diagnostic question + suggested first observation).

Fields: **Concept/Goal** (covers both "what is X" and "what is this supposed to do"), **Diagnostic question**, **Suggested observation**. Only populated fields render.

### Bright line — goal vs implementation (proposed, confirm)
Coach MAY explain **what the code is *supposed* to do** (goal/intended behavior, from topic + task) and **general concepts**. Coach must NOT describe **what the current (broken) code actually does**, **where it diverges**, or **the fix** — that divergence is what the user must discover (the learning).

### Research fit — the coach operationalizes the study's #1 behavior
The Anthropic RCT found **Conceptual Inquiry** (ask for the *why*, write/debug yourself) scored highest *and* fastest; the failure mode is the deadline-driven **slide into delegation**. The coach **removes the choice** — inside a check, conceptual help is the only channel open (patch withheld), so inquiry becomes the path of least resistance, not a discipline to summon. This makes **boundary (A) no-code research-grounded, not taste**: withholding the implementation is *what forces* the conceptual mode; a coach that could see/quote code slides back toward generation. Maps further to: generation-then-comprehension (Ledger = the comprehension step, applied retroactively), don't-let-AI-rob-you-of-errors (Debug-to-Own re-manufactures the error), attempt-first/AI-as-reviser, metacognitive-mirror (the reflection step). **Pitch: Anthropic is the anchor; broader literature is corroborating color only** (`Ledger.md:215`). Metacognitive-mirror beat now rides the **coach's diagnostic questions + the check itself** (standalone reflection step cut 2026-06-19).

### Coach input boundary — LOCKED: (A) no code
Coach receives only **topic description + Task + failing-test output** — never the original implementation, mutation diff, intended patch, or target line (`Ledger.md:107`); tools denied so it cannot fetch them. Withholding is *architecturally true*, and (per Research fit) it's what forces the conceptual mode.

### Interaction & execution — LOCKED
- **Interaction:** chat-thread; each reply = a structured card (only populated fields shown); **patch-refusal = a designed moment**, not an error.
- **Execution:** **live-but-rehearsed** `claude -p` (real call, all tools denied; driven by 1–2 rehearsed questions for the demo; free-form input built but not demoed).

## Reflection — CUT (2026-06-19)

No post-green reflection step. **Cut by Owen:** low UX/demo value — typing into boxes after the fix is friction + anticlimactic, and the canonical demo already minimized it to one question with the payoff in persistence. After green → persist → Topic page history directly.

_Consequences:_
1. Drops the "combines all **three** study mechanisms" pitch claim (`Ledger.md:149`). Ledger now leans on **encounter-the-error** (the check) + **ask-conceptual-questions** (the coach); explain-after-generation is no longer a built step.
2. The metacognitive-mirror beat rides the coach's diagnostics + the check itself.
3. Struggle-grading proof survives via the history (`elapsed · runs · conceptual help · no solution given · code snapshot`) — minus "reflection captured."
4. Demo 2:25–2:45 becomes persistence-only (return to Topic page, show history); frees ~15s.

**Ledger.md needs reconciliation:** `:144–149` (Completing a check), `:149` (three-mechanisms claim), `:177` (demo sequence). Offered separately.

## Visual tone — LOCKED (2026-06-19)

Calm professional **dev-tool register** (Linear / Vercel / GitHub-settings), info-dense but legible. **Never gamified** — no score, badges, streaks, confetti (contradicts "tests the person, doesn't grade the code").
- **Dark mode** primary (dev-native; matches the Claude Code context).
- **Restrained palette, one accent.** **Semantic red/green reserved strictly for test pass/fail** — debt/flags render calm and neutral ("check recommended"), never alarm-red.
- **Mono** for code + signal chips; **sans** for UI.
- **Microcopy:** professional, lightly opinionated (the coach), never accusatory. "Ownership check recommended," never "you don't understand."
- **Anthropic kinship, not impersonation:** warm-neutral register adjacent to Anthropic's aesthetic to reinforce Claude-Code-native — but NO Anthropic logos / exact brand colors / fake-official look.

## Demo display — LOCKED (2026-06-19)

**Laptop, primary.** Build desktop layouts first (Topic page = dominant-left + stacked-right; workspace = 3 columns). Vertical-stack responsive fallback exists for narrow/projector but is not the demo target.

## Intentionally light (not forgotten)
- **Vision preview** = a single static, narrate-only panel (Learning preview). Not interactive.
- **Loading/empty states** = standard; the few that matter for the demo: *creating sandbox*, *running checks*, *coach thinking*.

## Spec status: COMPLETE (2026-06-19)
All interaction + layout decisions locked — ready to feed the claude.ai design interface. Pending (optional): Ledger.md reflection reconciliation (`:144–149, :149, :177`).
