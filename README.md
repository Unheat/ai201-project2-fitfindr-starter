# FitFindr 🛍️

FitFindr is an LLM-driven agent that helps you find secondhand fashion items, style them
against your existing wardrobe, and write a shareable "fit card" caption. It runs on the
Groq API (`llama-3.3-70b-versatile`) with a Gradio web interface.

The core idea: **the agent decides which tools to run based on what you actually ask for.**
Asking only to find an item runs only the search; asking for styling or a caption runs the
extra tools. The three tools are independent — they are not hard-wired into a fixed chain.

---

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Running it

```bash
python app.py
```

Open the URL printed in your terminal (it is usually `http://localhost:7860`, but the port
can differ — read the terminal output). You can also run the agent directly from the CLI for
a quick check:

```bash
python agent.py
```

---

## Tool Inventory

All three tools live in [tools.py](tools.py). The agent calls them through the dispatcher in
[agent.py](agent.py) (`dispatch_tool`), which manages shared state between calls.

### 1. `search_listings`

| | |
|---|---|
| **Purpose** | Find secondhand items in the mock dataset that match the user's description, optional size, and optional price ceiling. |
| **Inputs** | `description` (str, required) — keywords like `"vintage graphic tee"`. `size` (str, optional) — e.g. `"M"`; matched case-insensitively as a substring so `"M"` matches `"S/M"`. `max_price` (float, optional) — inclusive price ceiling. |
| **Output** | `list[dict]` of matching listings sorted by relevance (best first). Each listing dict has `id, title, description, category, style_tags, size, condition, price, colors, brand, platform`. Returns `[]` when nothing matches — it never raises. |

Matching is keyword-overlap scoring: the description is tokenized, each listing's searchable
text (title + description + category + colors + tags) is scanned, and a listing is kept only
if it matches at least `MATCHING_THRESHOLD` (0.6) of the query tokens.

### 2. `suggest_outfit`

| | |
|---|---|
| **Purpose** | Build 1–2 complete outfit combinations around the found item, using the user's saved wardrobe as context. |
| **Inputs** | `new_item` (dict) — the selected listing. `wardrobe` (dict) — the user's wardrobe with an `items` list. **Note:** the LLM calls this tool with *no arguments*; the dispatcher injects `selected_item` and `wardrobe` from session state (see State Management). |
| **Output** | `str` — natural-language outfit suggestions. If the wardrobe is empty, it gives general styling advice using universal basics instead of failing. |

### 3. `create_fit_card`

| | |
|---|---|
| **Purpose** | Turn the outfit advice into a short, casual, shareable social-media caption. |
| **Inputs** | `outfit` (str, required) — the styling text. `new_item` (dict) — injected by the dispatcher from `selected_item`. |
| **Output** | `str` — a 2–4 sentence OOTD-style caption that names the item, price, and platform. Returns a safe fallback string if `outfit` is empty (never raises). |

---

## How the Planning Loop Works

The loop lives in `run_agent()` in [agent.py](agent.py). It is **not** a fixed
"always run all three tools" script. Instead it is an LLM tool-calling loop where the model
decides what to do, and the **decisions** are what matter:

1. **Build the session and message history.** `_new_session()` creates the session dict and a
   message list seeded with the FitFindr system prompt plus the user query. If `chat_history`
   from a previous turn is passed in, it is reused so the agent remembers earlier context
   (e.g. a size mentioned two turns ago).

2. **Ask the LLM what to do.** Each round calls Groq with the full message history, the three
   tool definitions, and `tool_choice="auto"`. The system prompt and tool descriptions tell the
   model to call **only the tools the user asked for** — search to find an item, `suggest_outfit`
   *only* if styling was requested, `create_fit_card` *only* if a caption was requested.

3. **Branch on the model's response:**
   - If the model returns plain text (no tool call), that is the final answer — store it in
     `session["final_reply"]` and stop.
   - If the model returns one or more tool calls, dispatch each through `dispatch_tool()`,
     append the JSON results back into the message history, and loop again so the model can
     react to what the tools returned.

4. **The search result drives the next decision.** When `search_listings` returns `[]`, the
   model sees the empty list and responds with a helpful no-results message — it does *not*
   fabricate an item or push on to styling. When results come back, the top one is saved and
   the model continues only if the user asked for more.

5. **Stop conditions.** The loop ends when the model gives a final text reply, or after
   `MAX_TOOL_ROUNDS` (10) as a runaway-guard. If the cap is hit with no reply,
   `session["error"]` is set.

**The decisions the agent makes**, in plain terms: *Did the user ask to find something?* (search)
→ *Did they ask how to wear it?* (suggest_outfit, but only after a search succeeds) → *Did they
ask for something to post?* (create_fit_card, but only after an outfit exists). Each is gated on
both user intent and the availability of the prerequisite data.

### Observed behavior (real runs)

| Query | Tools the agent chose to call |
|---|---|
| `vintage graphic tee under $30` | `search_listings` **only** |
| `find a vintage graphic tee under $30, suggest an outfit, then make me a fit card` | `search_listings` → `suggest_outfit` → `create_fit_card` |
| `90s track jacket in size M, and give me outfit ideas` | `search_listings` → `suggest_outfit` (no fit card — none requested) |
| `designer ballgown size XXS under $5` | `search_listings` **only** (no results → graceful reply) |

---

## State Management

A single **session dict** (created in `_new_session()`) is the source of truth for one
interaction. Tools never talk to each other directly — they read from and write to the session
via `dispatch_tool()`. This is what lets the user avoid re-typing the listing or outfit between
steps.

Key fields:

- `messages` — the full LLM conversation (system + user + assistant + tool results). This is
  what carries chat history across turns.
- `selected_item` — set by the dispatcher to the **top** result of `search_listings`.
- `wardrobe` — stored once at session creation.
- `outfit_suggestion` — set when `suggest_outfit` runs.
- `fit_card` — set when `create_fit_card` runs.
- `final_reply` — the model's closing text.
- `error` — only set if the loop exhausts `MAX_TOOL_ROUNDS` without a reply.

**How data flows between tools (visible in a real full-chain run):**

1. The LLM calls `search_listings({'description': 'vintage graphic tee', 'max_price': 30})`.
   The dispatcher saves `selected_item = "Y2K Baby Tee — Butterfly Print"`.
2. The LLM then calls `suggest_outfit({})` — **with no arguments**. The dispatcher fills in the
   saved `selected_item` and `wardrobe` itself, so the model can't accidentally style the wrong
   item or hallucinate one. The result is stored in `outfit_suggestion`.
3. The LLM calls `create_fit_card({'outfit': '...'})`; the dispatcher pairs that text with the
   saved `selected_item` to produce the caption stored in `fit_card`.

This dispatcher-injects-state pattern means the model only has to decide *whether* to call a
tool, not re-supply data it already produced — the session guarantees the right item is carried
forward.

---

## Error Handling (per tool, with a real example)

| Tool | Failure mode | What actually happens |
|---|---|---|
| `search_listings` | No listing matches | Returns `[]`. The agent feeds that to the LLM, which replies gracefully and **stops** — it does not move on to styling. |
| `suggest_outfit` | Wardrobe is empty | Detects the empty `items` list and switches to a general-styling prompt using universal basics, instead of failing. |
| `suggest_outfit` / `create_fit_card` | No item selected yet | The dispatcher guards on `session["selected_item"]` and returns `{"error": ...}` rather than calling the LLM with nothing. |
| `create_fit_card` | Empty/whitespace `outfit` string | Returns a safe fallback string before any API call. |
| `run_agent` (loop) | `MAX_TOOL_ROUNDS` hit with no reply | Sets `session["error"]` so the UI can show a clear failure message. |

**Concrete example from testing — the no-results path.** I ran:

> `designer ballgown size XXS under $5`

The agent called `search_listings({'description': 'designer ballgown', 'max_price': 5, 'size': 'XXS'})`,
which returned `[]`. The agent did **not** invent an item or call the styling tools. It replied:

> "No designer ballgowns in size XXS were found under $5."

`selected_item`, `outfit_suggestion`, and `fit_card` all stayed `None`. (Note: in this path
`session["error"]` remains `None` — the graceful no-results message comes from the LLM's reply,
not from the error field, which is reserved for the loop-exhaustion safeguard.)

**Concrete example — empty-wardrobe styling.** I ran `90s track jacket in size M, and give me
outfit ideas` against an **empty** wardrobe. `search_listings` found the *90s Track Jacket —
Navy/White Stripe*, and `suggest_outfit` recognized the empty wardrobe and returned advice built
around basics ("pair the navy/white stripe track jacket with a plain white tee and standard blue
jeans... neutral sneakers"), rather than erroring or hallucinating owned items.

---

## Spec Reflection

The spec asked for a planning loop that "behaves like a decision tree, not a fixed script."
My first working version technically had all three tools but the system prompt and tool
descriptions instructed the model to *always* chain search → outfit → fit card. In testing,
the query `vintage graphic tee under $30` (no mention of styling) still ran all three tools and
filled all three panels — behavior that contradicted the spec's intent.

The fix was not in the loop code but in the **instructions**: the tool descriptions literally
said "Call this after finding an item" / "Call this after receiving an outfit suggestion," which
the model read as commands to chain. Rewriting both the system prompt and the tool descriptions
to "call ONLY when the user explicitly asks" made the agent genuinely intent-driven, which the
observed-behavior table above confirms.

One place where the implementation **diverged from my original planning.md**: I had planned to
parse the query with Python regex and set `session["error"]` on no results. In practice I let the
LLM both parse the query (it fills in `description`/`size`/`max_price` as tool arguments) and
handle the no-results message itself. This is simpler and handles phrasing variation better, so
`session["parsed"]` ended up unused and `session["error"]` became a loop-safety net rather than
the no-results path. planning.md has been updated to match.

**Known rough edge (observed):** at `TEMPERATURE = 0.6`, `create_fit_card` occasionally restates
the price inaccurately in the caption (one run produced "$10" for an $18 item even though the
correct $18 appeared in the final summary). The caption is decorative, but a stricter prompt or
lower temperature for that tool would tighten it.

---

## AI Usage

I used Claude (in the IDE) at two specific points.

**1. Fixing the "always chains all three tools" bug.**
- *Input I gave it:* a screenshot of the running app showing all three panels populated for the
  query `vintage graphic tee under $30`, the contents of [agent.py](agent.py) and
  [tools.py](tools.py), and the requirement that the three tools be used independently based on
  user intent.
- *What it produced:* it identified that the system prompt's "always continue with suggest_outfit
  and create_fit_card" instruction *and* the tool descriptions' "Call this after finding an item"
  wording were both forcing the chain, and rewrote them to "call ONLY when the user explicitly
  asks."
- *What I changed/overrode:* I kept its prompt rewrite but tweaked the `suggest_outfit`
  description wording to mention combining with "the target piece," and I declined its suggestion
  to add a deterministic keyword-based tool gate as a backstop — I wanted the decision to stay
  with the LLM, and testing showed the prompt fix alone was enough.

**2. Writing this README from real test output.**
- *Input I gave it:* the Milestone 6 requirements, `docs/mistake_to_look_for.md` (which warns
  against describing expected instead of observed behavior), and the four files
  (agent/tools/app/planning).
- *What it produced:* it ran the agent on four real queries, captured the actual tool-call
  sequences and outputs, and drafted the README's tool inventory, planning-loop, state, and
  error-handling sections grounded in those real runs.
- *What I changed/overrode:* I reviewed every reported output against the real terminal logs and
  had it correct the no-results section to state honestly that `session["error"]` stays `None`
  on that path (the graceful message comes from the LLM reply), rather than the cleaner-sounding
  but inaccurate "it sets session['error']."

---

## Repo layout

```
ai201-project2-fitfindr-starter/
├── agent.py        # planning loop, tool definitions, dispatcher
├── tools.py        # the three tools
├── app.py          # Gradio interface (handle_query wires UI → run_agent)
├── config.py       # model, temperature, thresholds, max rounds
├── planning.md     # the design spec (kept aligned with the code)
├── data/
│   ├── listings.json
│   └── wardrobe_schema.json
└── utils/data_loader.py
```
