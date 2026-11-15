# Talking about Atlas in a job interview

Written for the five of us, for placement season rather than for the viva. The
viva document is [`../TEAM/faq.md`](../TEAM/faq.md) and it is a different job:
there, you are defending a claim. Here, you are showing how you think.

---

## The 60-second version

> It's a graph of which public companies depend on which others, built only from
> public regulatory filings. The interesting part is that you can't get it from
> the obvious direction - a big buyer never publishes its supplier list. But a
> small supplier is legally required to disclose a customer worth more than 10%
> of its revenue. So we read thousands of small companies and invert what they
> say.
>
> The constraint we set ourselves was that every single edge has to cite the
> sentence that proves it - that's enforced as a `NOT NULL` foreign key in the
> schema, not a convention. And we audited it: we hand-judged 86 relationships
> against the actual filings and measured 100% precision where a percentage is
> disclosed, 68% where it's only a name.

Stop there. Everything after this depends on which part they pick up.

## Which part they pick up tells you who you're talking to

- **"How did you measure that?"** → a strong engineer. Go to the evaluation.
- **"What's the business model?"** → product or founder. Go to the asymmetry and
  who pays to defend a conclusion.
- **"Why Postgres and not Neo4j?"** → a systems interviewer checking whether you
  chose or defaulted.
- **"Where's the AI?"** → go straight to what the model is *not* allowed to do.
  This is the answer that separates you from everyone else's LLM project.

---

## The four stories, with the shape that makes them land

Each one: situation, what you did, what the number was. Keep them under two
minutes.

### Story 1 — "I measured my own work and it was worse than I thought"

We built the whole extraction pipeline, got 803 edges out, and it looked
finished. Then I drew a random sample and read the cited sentences by hand.
62.5% were correct.

The failures were systematic, not random: we were uppercasing text before
matching company names, so "financial institutions" matched a company called
Financial Institutions. And "we are a supplier to Ford" was being read as us
depending on Ford - backwards.

We ended with 194 relationships from 803. The system got better by having
things removed.

**Why it lands:** very few graduates have ever measured their own output and
published the number. The ones who have are immediately distinguishable.

### Story 2 — "The bug that was invisible until someone read the data"

Our system displayed things like "SoftBank: 57% of revenue". The sentence
actually said "our top five customers *collectively* accounted for 57%". We were
copying a group total onto every company named in the list. 16 of 36 displayed
percentages were wrong that way.

The fix was three rules: a figure introduced as a total belongs to the group; a
figure that follows a name beats one that precedes it; and no figure belongs to
a company if another company's name sits between them. We went to 20 of 21
correct, and we now withhold a figure entirely rather than guess.

**Why it lands:** it's a correctness bug that no test would have caught, because
every unit test would have passed. It shows you know the difference between
"the code works" and "the output is true".

### Story 3 — "Choosing measurement over a heuristic"

We needed to tell generic phrases apart from real company names. "Financial
Institutions" is generic; "Applied Materials" is a real company. Both are
ordinary English, so a dictionary cannot help.

Instead of guessing, we measured: a company name is written capitalised nearly
every time it appears in a corpus; a generic phrase isn't. We counted both forms
across all 225 filings. Nasdaq appeared in 53% of them - removed. "Wearable
Devices" was lowercase in 12 of 12 occurrences - removed. Boeing and Applied
Materials kept.

**Why it lands:** it's the instinct to replace an argument with a measurement,
which is most of what good engineering is.

### Story 4 — "Designing a constraint we couldn't cheat on"

Our whole product is the promise that every claim is traceable. We could have
enforced that in code, but code gets a second path added under deadline. So we
put it in the schema: an edge without a source chunk cannot be inserted. And
every read of the graph goes through one function that filters by publication
date, so we can't accidentally use information that wasn't public yet.

**Why it lands:** it's an architecture answer about human failure modes, not
about frameworks.

---

## Questions you will get, and the answer

**"Isn't this just scraping?"**
Fetching is the easy part. The work is inverting an asymmetry nobody publishes
directly, resolving names to entities, getting the direction right, and
measuring how often we're wrong.

**"Why didn't you just use GPT for all of it?"**
For reading one sentence into structure, we should and the interface is built
for it. But the model is not allowed to score anything or to produce the
citation, because then nothing is reproducible and we can't say why a number is
what it is. Scoring is deterministic and versioned.

**"68% doesn't sound very good."**
It isn't, for that tier, and we publish it. The tier where a percentage is
disclosed measured 26 of 26, and the product leads with that. A system that's
68% and knows it is more useful than one that feels accurate and has never been
checked.

**"What would you do differently?"**
Measure earlier. We built everything before auditing a single edge, and the
audit changed our understanding of our own system more than any feature did.

**"What was your specific contribution?"**
Answer with your area from [`../TEAM/ownership.md`](../TEAM/ownership.md) and one
concrete problem you personally solved. Never claim the whole system - two
follow-up questions will expose it, and that is the only unrecoverable mistake
in this list.

---

## Mistakes to avoid

- **Saying "the AI builds the graph."** It doesn't, and this is the most
  common way a candidate flattens their own interesting project into everyone
  else's chatbot.
- **Quoting a number you can't source.** If you say 68%, be ready for "how did
  you measure that". If you aren't, say "we measured it, I'd have to check the
  exact figure".
- **Hiding the failures.** Volunteering the Broadcom/VMware failure is worth more
  than defending a perfect record nobody believes.
- **Leading with the globe.** It's the prettiest part and the least interesting.
  Lead with the asymmetry.

## If they want to see it

```bash
make dev && make api && make web     # :5173, :8000
```

Show them one company with a disclosed percentage - Ducommun, or Dauch - and
click through from the edge on screen to the sentence on the SEC's own servers.
That click is the whole product.
