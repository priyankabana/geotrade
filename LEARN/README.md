# Finance from zero, for people who write code

You do not need a finance degree to work on Atlas. You need to be able to open a
10-K and find the three sentences that matter. This is the path to that, in
order, with nothing in it you can skip.

If a term is new, it is in [`glossary.md`](glossary.md). No term is used twice in
this repo before it has an entry there.

---

## Hour 1 — What a filing even is

A public company has to tell the public certain things on a schedule. In the US
that happens through **EDGAR**, the SEC's filing system, which is free and
machine-readable. That last fact is why this project exists at all.

The forms we care about:

| Form | What it is | Why we read it |
|---|---|---|
| **10-K** | the annual report | where customer concentration is disclosed |
| **10-Q** | the quarterly | updates, less narrative |
| **8-K** | "something happened" | plant fires, contract losses, sudden events |
| **20-F / 40-F** | the annual for foreign issuers | same content, different structure |

**Do this now:** open any 10-K on EDGAR. Pick a small company, not Apple. Scroll
until you are bored. The point is to see how much of it is boilerplate, because
that is what stage one of our pipeline exists to throw away.

---

## Hour 2 — The three places dependency hides

A 10-K is divided into numbered Items. We read three of them.

**Item 1, Business.** Prose. Describes what the company does and who it does it
with. This is where you find "our largest customers are Ford, GM and Stellantis"
and "we purchase our engines on a single-source basis from Cummins".

**Item 1A, Risk Factors.** The company listing everything that could go wrong.
Legally defensive, deliberately long, and full of dependency statements because
dependency *is* risk: "we rely on a single supplier for...".

**Item 7, MD&A.** Management explaining the numbers. Concentration often appears
here with a figure attached.

Plus the **notes to the financial statements**, where a "concentration of credit
risk" note says things like "one customer accounted for 100% of revenue".

**Do this now:** in the 10-K you opened, use Ctrl-F for `accounted for`. Then
`10% of`. Then `single source`. You have just done by hand what `extract.py`
does across 14,738 chunks.

---

## Hour 3 — Why anyone is forced to tell us

This is the single idea the whole project rests on, so slow down here.

A company must disclose a customer that represents a **material** share of its
revenue, because a reasonable investor would want to know that losing one
customer would take a third of the business with it. In US practice the
threshold is generally **10%**.

Now notice the asymmetry:

- Ducommun is small. Boeing is 13% of its revenue. Ducommun **must** name Boeing.
- Boeing is enormous. Ducommun is a rounding error to Boeing. Boeing **never**
  names Ducommun, and has no reason to.

So the relationship exists in exactly one direction in public text: **the small
company names the large one.** Read enough small companies and the large
company's supplier base assembles itself.

That is the inversion. Everything else in Atlas is engineering around it.

**The limit, which you must be able to state:** we only see a relationship when
one side is small enough that the other side is material to it. Two giants
trading with each other are invisible to us. That is structural.

---

## Hour 4 — The numbers you will meet

You do not need accounting. You need these, and the glossary has the rest.

- **Revenue** - money in from selling things. Our percentages are usually a
  share of this.
- **Net sales** - revenue after returns and discounts. Filings use both terms;
  treat them as the same for our purposes and record which one the sentence
  used.
- **Accounts receivable** - money owed but not yet paid. A concentration figure
  can be a share of *this* instead of revenue, which is a different fact about a
  different risk. This is why we store `materiality_text` and never show a
  percentage without its basis.
- **Segment** - a named part of a business. "37% of AEC's net revenues" is a
  share of one segment, not of the company.
- **Fiscal year** - a company's own 12-month accounting year, which often is not
  the calendar year.

**Why this matters to our code:** "44%" is not a fact. "44% of our consolidated
net sales in 2025" is. Our audit found that attaching the right number to the
wrong basis - or to the wrong company entirely - was the single worst defect in
the system. See [`../eval/README.md`](../eval/README.md).

---

## Hour 5 — Look-ahead bias

The one idea that separates a credible analysis from a worthless one.

If you use information to explain an event, and that information was not public
when the event happened, your result is meaningless. It will also look
*excellent*, which is what makes it dangerous.

A 10-K filed in February 2026 tells you about a relationship as it stood in
2025. You may not use it to explain anything that happened in 2024.

Atlas enforces this structurally: every edge carries `valid_from`, and every
read goes through `edges_as_of(timestamp)`. There is deliberately no second
path, because a rule you have to remember is a rule you will forget.

**Do this now:** in the running app, switch to Replay and pick the Ever Given
event, March 2021. Zero companies. Read the message the UI shows. That is the
rule working, not a bug.

---

## Hour 6 — Read our own output

Open [`../eval/concentration_all.txt`](../eval/concentration_all.txt). It is
every concentration-backed relationship in the graph with the sentence behind it.

Read ten of them and decide for yourself whether each is right. You will find
the judgement is usually easy and occasionally genuinely hard - and when you hit
a hard one, you have found exactly where the remaining work is.

Then open [`../eval/README.md`](../eval/README.md) and compare your verdicts
with ours.

---

## What to read outside this repo

- **SEC EDGAR full-text search** - the fastest way to see how a phrase like
  "accounted for approximately" appears across thousands of real filings.
- **Any one 10-K, read end to end, once.** It is dull and it is worth it. You
  will never again be surprised by the structure.
- **"Financial Statements: A Step-by-Step Guide"** or any equivalent - only if
  you want the accounting. For Atlas you do not need it.

## What you can safely ignore

Valuation. Ratios. Discounted cash flow. Portfolio theory. Options. None of it
touches this project, and Atlas makes no investment recommendations, so none of
it is coming.
