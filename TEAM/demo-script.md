# Demo script

Three versions. The 90-second one is recorded at [`../demo/atlas-demo.mp4`](../demo/atlas-demo.mp4)
and plays on mute. The five-minute one is for a live walkthrough. The last section is for
when something breaks, which it will.

Re-record any time with `make demo` — it drives the real app against the real database,
so if the app is broken the video is broken. That is deliberate.

---

## The recorded version (5 minutes, narrated)

[`demo/atlas-demo.mp4`](../demo/atlas-demo.mp4). Nine animated explainer slides, then the
live application, then two closing slides. It has a voice track and on-screen captions,
so it works with sound on or off.

Re-record after any change with `make demo`; it drives the real app against the real
database, so a broken app makes a broken video. That is deliberate.

**The voice is macOS system speech** (`say`, voice Daniel). It is clear and audibly
synthetic. Change it with `ATLAS_VOICE=Samantha make demo` — `say -v '?'` lists what is
installed. **For the actual submission, record one of you reading the same lines.** A real
voice beats any of these, the script is `scripts/record_demo.py` → `NARRATION`, and the
timing adjusts to whatever you record because the video paces itself to the audio.

Learn this. You will be asked to narrate it live.

> Atlas. A map of which public companies depend on which others — built only from what
> those companies have already disclosed in public.
>
> 23,380 companies across six markets: the US, India, the UK, Germany, Canada and
> Australia. Every bar is headquarters, binned by density, live from Postgres.
>
> Coverage by country, counted from the database. Pick one. Sectors counted from the
> data, not a hardcoded list. Semiconductors — the sector where small suppliers name
> their large customers. Real companies, with real identifiers behind each one.
>
> Now the part that matters. Replay a real disruption. An event in the Taiwan Strait,
> and the arcs are the dependency chain reaching outward — across the Pacific, and down
> into India. Blue is the names you would not have listed yourself; five of the seven
> here are two or three hops out. Each hop carries the exact sentence that proves it.
> If we cannot show you the sentence, we do not make the claim.
>
> The timeline is the backtest. Scrub to any past disruption and the graph is read as it
> stood that morning, never with anything filed later.
>
> And we are explicit about what is not built. Extraction has not run, so these edges are
> a worked example — the app says so on screen. The data layer is real and running today.

**Say this out loud before anyone asks:** "Companies, tickers and coordinates are real and
in the database. The dependency edges are illustrative and the scores come from a stub
scorer. That screen shows the shape of the answer, not an answer."

---

## The 90-second cut

If you only have ninety seconds, open on the globe, go straight to Replay, and say:

> Atlas is a map of which public companies depend on which others, built only from what
> those companies have already disclosed in public.
>
> Every dot is a company headquarters. 1,958 of them, read live out of Postgres.
>
> Click a country, and you get thirty-nine sectors counted from the database. Go into
> semiconductors — the sector where small suppliers name their large customers, because a
> marquee customer is their best credential.
>
> Every company traces back to its filing: CIK, headquarters, fiscal year end, former
> names, all pulled from SEC EDGAR, nothing typed by hand.
>
> Now the part that matters. An event in the Taiwan Strait. The arc crosses the Pacific to
> companies in California. The blue diamonds are two hops out — the ones you would not have
> listed yourself. And each hop carries the exact sentence that proves it. If we cannot show
> you the sentence, we do not make the claim.
>
> We are also honest about what is not built. Extraction has not run, so there are no real
> edges yet, and the app says so on screen rather than implying coverage we do not have.

**Say this at the end, out loud, before anyone asks:** "The companies, CIKs and filing dates
are real. The quoted sentences are placeholders and the scores come from a stub scorer.
That screen shows the shape of the answer, not an answer."

---

## The five-minute live version

### 0:00–0:45 — The problem, with no jargon

Do not open the laptop yet.

> When a port closes or a factory burns down, everyone knows which companies are obviously
> affected. What nobody has is a list of the companies affected *next* — the ones that
> quietly buy something from the companies that got hit.
>
> The obvious way to build that list is to read big companies' filings and extract their
> suppliers. It does not work. Supplier lists are commercially sensitive, so a big company
> writes "certain suppliers" and "a limited number of vendors."
>
> So we inverted it. Big companies hide their suppliers, but small suppliers **advertise**
> their big customers, because a marquee customer is their main credential — and accounting
> rules force them to disclose any customer over 10% of revenue. The edge you cannot get
> from the buyer, you get free from the seller.

### 0:45–1:30 — The evidence that it works

> We did not assume that. We measured it before building on it. We pulled ten real
> semiconductor 10-Ks and ran a zero-cost keyword-and-gazetteer pass. Ichor Holdings' filing
> named Lam Research and Applied Materials six times each. Ultra Clean's named the same pair.
> No model involved.
>
> And it is mechanical, not manual. EDGAR has a full-text search. Search it for a big
> buyer's name and what comes back is not their filings — it is the filings of the small
> companies who named them as a customer. The whole thesis is one free API call.

### 1:30–3:00 — The app

Open it. Follow the recorded order: globe → United States → semiconductors → a company →
the worked example.

Points to land while clicking:

- **On the globe.** "1,958 headquarters, live from the database. Drag it."
- **On the sector list.** "Counted from the data. If we load another market tomorrow this
  list changes with no code change."
- **On the company.** "CIK, fiscal year end, former names. Former names matter — an old
  filing uses the old name, and if you miss that you split one company into two."
- **On the worked example.** "Red is the event. Blue diamonds are two hops out. Each hop
  carries its sentence." Then the honesty line above.

### 3:00–4:00 — The engineering

> Three constraints are enforced in the schema rather than in code review.
>
> One, `dependency_edge.chunk_id` is `NOT NULL`. There is no way to write an edge without a
> citation, even by accident.
>
> Two, the model never produces a score. It reads a sentence and reports what the sentence
> says, with character offsets. Confidence and exposure weight come from versioned,
> unit-tested code. If you ask how it decided, the answer is an algorithm, not "we asked an AI."
>
> Three, every edge carries the date it became public, and every read goes through one
> function that filters on an `as_of` timestamp. That stops look-ahead bias — using a 2026
> filing to "predict" a 2021 event. It is the standard way research products embarrass
> themselves, and a reviewer catches it with one question: what date does your graph query use?

### 4:00–4:40 — Cost, because it is the surprising part

> Our budget is zero rupees. So we measured what a full extraction costs instead of guessing.
> Ten real filings: section targeting removes 46% of each document for free, then a non-LLM
> filter passes 28% of what is left. We put about 15% of each filing in front of a model.
>
> That is roughly 5,000 model calls for the full corpus — an overnight run on one laptop,
> under an hour for the pilot. Which means we can change the prompt and re-extract weekly
> without anyone hesitating. That is the whole reason extraction ever gets good.

### 4:40–5:00 — What is next, honestly

> What exists is the data layer: 2,002 companies, 9,635 aliases, the schema, the API, the
> frontend. What does not exist is extraction. That starts with a validation experiment in
> week three where five of us hand-annotate forty documents, with the decision rules written
> down before we read any of them.
>
> If the yield is bad we change the sector, and we will have found that out in week three
> instead of week thirteen.

---

## When it breaks on stage

It will. Stay calm and keep talking — an examiner judges the recovery, not the failure.

| What breaks | What you say | What you do |
|---|---|---|
| **API is down** | "The frontend falls back to fixtures when the API is unreachable — and tells you it has, at the top of the screen. That is deliberate; a demo that cannot tell you whether its numbers are real is worse than no demo." | Keep going. The banner proves the point. |
| **Docker is not running** | "The database runs in a container; let me start it. Meanwhile here is the recorded version." | `make db` in another terminal, play the video. |
| **Globe will not load** | "The geometry loads lazily — there is a 2D path too. The map is a view onto the data, not the data." | Use the panel; it works alone. |
| **Blank panel / loading forever** | "That is a real bug and I will show you the logs rather than guess at it." | Open the console. **Never invent an explanation.** |
| **Someone asks for something not built** | "Not built. It is phase three, and here is the roadmap entry." | Open `docs/ROADMAP.md`. |
| **Total failure** | "The machine is not cooperating. Let me show you the recorded demo and then take you through the code." | `demo/atlas-demo.mp4`. **Always have it on the desktop.** |

**The rule: never claim something works that you have not just seen work.** One recovered
failure costs you nothing. One number you cannot defend costs you the room.

---

## Questions you will get, and short answers

**"So it is a RAG app with a map on it?"**
No. A RAG app retrieves text to answer a question. We build a persistent, queryable graph
where every edge is a row with a citation and a validity period, and the scoring is
deterministic code we can show you. The retrieval is the easy part.

**"Companies do not name their suppliers. How do you have a graph at all?"**
They do not — which is why we build it from the other end. Small suppliers name their large
customers, and the 10% revenue rule forces the disclosure. We measured it on ten real
filings before we built anything.

**"Your filings are nine months old. Is that not fatal?"**
Two separate layers. Filings give structure — who depends on whom — and dependencies move
slowly. News gives state, and that is live. Structure being months old is fine; that is why
we keep them apart.

**"How do you know your graph is right?"**
Partly we do not, which is why every claim shows its source sentence so you can check it
yourself. Measurably: precision and recall against a human-annotated golden set, in CI on
every change.

**"What is your accuracy?"**
We do not have one yet, because extraction has not run. I am not going to give you a number
we have not measured. What I can tell you is what we measured: 46% of each document removed
by section targeting, 28% filter pass rate, ten documents, reproducible with `make measure`.

**"What did you personally write?"**
Have a real answer ready. Name files.
