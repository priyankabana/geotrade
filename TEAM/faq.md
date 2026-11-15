# Defending Atlas: every question we expect, and the honest answer

Written for the five of us, to be read before the review and before the viva.

Rules we hold to in this document:
- If the honest answer is "we don't know", that is the answer. An examiner
  respects a bounded claim and destroys an unbounded one.
- Every number here comes from `eval/README.md` or from a script in this repo.
  If you quote a number you cannot point at, you will be asked to, and you will
  not have it.
- Never say "the AI figures it out". The model never scores anything in Atlas.
  If you say it does, you have contradicted the architecture in one sentence.

---

## 1. The idea

**Q1. In one sentence, what is Atlas?**
A graph of which public companies depend on which other public companies, built
only from what companies have already disclosed in public filings, where every
single edge carries the sentence that proves it.

**Q2. Why is that hard? Isn't it just reading annual reports?**
Because the information is deliberately asymmetric. A large buyer has no reason
to publish its supplier list and every reason not to. We never get it from the
buyer's side.

**Q3. Then where does it come from?**
From the other end. A small supplier is *required* to disclose a customer who
represents a material share of its revenue - in US filings, generally 10% or
more. So the small company names the large one. We read the small companies and
invert what they say.

**Q4. Give me a concrete example.**
Ducommun is a small aerospace parts maker. Boeing does not list Ducommun
anywhere. But Ducommun's 10-K says Boeing generated 13% of its 2025 net
revenues, because it must. We now have a Ducommun -> Boeing edge, sourced from
Ducommun, about Boeing.

**Q5. Why is this called bottom-up?**
Because the direction of discovery is from small to large. The graph assembles
itself out of thousands of small disclosures rather than from any single
authoritative list, which does not exist publicly.

**Q6. So the graph is biased toward relationships involving small companies?**
Yes, and we say so. We see a relationship only when one side is small enough
that the other side is material to it. Two giants trading with each other are
invisible to us. That is a structural limit of the method, not a bug we will
fix.

**Q7. Why would anyone pay for this?**
Because concentration risk is the kind of risk that is knowable in advance and
still surprises people. When a plant burns down, the question "who else is hurt"
currently takes analysts days. We answer it in milliseconds, with citations.

**Q8. Isn't this just a supply chain database? Those exist.**
The commercial ones exist, cost a great deal, and are largely unsourced - you
get an assertion, not a sentence. Our differentiator is not coverage, which is
smaller than theirs. It is that every claim is falsifiable by clicking through
to the filing.

---

## 2. The citation guarantee

**Q9. What exactly does "every edge cites its source" mean technically?**
`dependency_edge.chunk_id` is `NOT NULL` in the schema, with a foreign key to
`chunk`. An edge without a source sentence cannot be inserted. It is not a
convention we follow; it is a constraint the database enforces.

**Q10. Why put it in the schema instead of in the code?**
Because code gets changed under deadline and schemas get changed deliberately.
If the guarantee lives in a code path, someone adds a second code path. If it
lives in a `NOT NULL`, the insert fails.

**Q11. Could you store a fake chunk to satisfy the constraint?**
We could, which is why the chunk also carries character offsets into a document
whose URL points at the regulator's own servers. The citation is checkable by a
third party without asking us for anything.

**Q12. What is a chunk?**
A span of text from a filing, with its document, its section, and its character
offsets. Chunks are 4800 characters with 600 of overlap so a sentence is never
cut in half at a boundary.

**Q13. Show me the path from a pixel on screen to a regulator's server.**
The UI shows an edge. The edge carries `citation.sourceUrl`, `charStart` and
`charEnd`. The URL is the SEC's own document. The offsets locate the sentence
within it. Nothing in that chain passes through us.

---

## 3. The model, and what it is not allowed to do

**Q14. Where is the AI in this?**
In exactly one place: stage two of extraction, which reads a single sentence and
returns structured claims. Nowhere else.

**Q15. Does the model decide how important a relationship is?**
No. Scoring is deterministic, versioned code - `scorer_version` is stored on
every edge. The same inputs produce the same score forever. A model that scored
things would make the graph unreproducible and unauditable.

**Q16. Why does that distinction matter so much to you?**
Because the product's only real asset is trust. If a model assigns the numbers,
then when a number is wrong we cannot say why, cannot reproduce it, and cannot
fix it in a way that proves it is fixed.

**Q17. What does the model actually return?**
Which company is named, whether it is upstream or downstream, the relationship
class, tense, substitutability, and a percentage if the sentence states one. It
explains and extracts. It never ranks and never recommends.

**Q18. Which model are you using right now?**
None. Stage two currently runs on deterministic rules, because the project
budget was zero when it was built. `extract_sentence` has a fixed input and
output shape precisely so the body can be swapped for a schema-forced model call
without touching anything else.

**Q19. Isn't "we didn't use AI in our AI project" a problem?**
Only if we hide it. We measured what the rules version achieves, found its
ceiling, and documented exactly which failures need a model to fix. That is a
stronger result than an unmeasured model call.

**Q20. What would change if you plugged a model in tomorrow?**
The function body of `extract_sentence`. Not the schema, not the citation
guarantee, not the scorer, not the API, not the UI. The offsets come from the
sentence, not from the model, so the citation holds either way.

---

## 4. Measured quality - the section that decides the viva

**Q21. How good is your extraction?**
Two tiers, measured separately. Where the filing states a percentage, we judged
all 26 relationships by hand and all 26 were correct. Where the filing names a
counterparty without a figure, we judged a random sample of 60 and 41 were
correct - 68.3%.

**Q22. Why two different numbers?**
Because they are genuinely different kinds of evidence and it would be
misleading to average them into one figure. A disclosed percentage is a hard
fact in a structured sentence. A name in a prose paragraph is not.

**Q23. 68% sounds low. Why should I trust the system?**
Because we know it is 68%, we know which 32% fail and why, and the product does
not present the two tiers as equal. The alternative - an unmeasured system that
feels accurate - is the actually dangerous one.

**Q24. How did you measure it? Be specific.**
`scripts/sample_pairs.py` draws a seeded random sample and writes it to disk
*before* any judging happens. Then we read each cited sentence and decided
whether it really states that dependency. The sample file is in the repo.

**Q25. Why write the sample before judging it?**
So the set under test cannot be quietly reshaped by what the judging turns up.
If you judge and sample at the same time it is very easy, and very human, to
drop the awkward ones.

**Q26. Who judged them? Isn't that biased?**
We did, which is a real limitation. The mitigation is that the sample and every
judgement are in the repo, so anyone can check our work against the same
sentences.

**Q27. What was it before you started fixing things?**
62.5%. The first audit of 80 relationships found 50 correct.

**Q28. What was the single worst defect you found?**
Percentage attribution. Sentences like "our top five customers collectively
accounted for 57% of revenue" were having that 57% copied onto every company
named in the list. Only 20 of 36 displayed percentages were right.

**Q29. And now?**
20 of 21 are right, and 5 figures are withheld entirely because the sentence
does not let us attribute them safely. The system now says nothing rather than
something wrong.

**Q30. How did you fix it?**
Three rules. A figure introduced as a total belongs to the group, not to each
member. A figure that follows a name outranks one that precedes it. And no
figure can belong to a company if another company's name sits between them - in
"Daimler AG 18% PACCAR Inc. 11%" that is the whole difference.

**Q31. What is your recall? How much do you miss?**
We have not measured recall rigorously and we will not claim a number for it.
We know the structural bound: we can only see relationships that someone was
required to disclose, which in the US means roughly the 10% threshold.

**Q32. That's a big gap in your evaluation.**
It is, and it is the first thing we would do next. Measuring recall means
finding every "accounted for X%" disclosure in a set of filings by hand and
checking how many we captured. We ran out of time, not out of method.

**Q33. Are these numbers optimistic?**
The narrative number probably is, by a point or two. We derived several fixes
from reading the first sample, and with only 179 relationships in that tier a
fresh sample necessarily overlaps it. We say this in `eval/README.md`. The
concentration number is not optimistic because it is exhaustive - 26 of 26 is
the whole population, not an estimate.

**Q34. Give me a failure you did not fix.**
Broadcom shows an edge to VMware. Broadcom bought VMware, so VMware appears in
Broadcom's filings as a product line, not a counterparty. No sentence-level rule
can know that. It is an entity-resolution problem, not an extraction one.

**Q35. Another one.**
"ISTAR" in Elbit Systems' segment table is a military acronym - Intelligence,
Surveillance, Target Acquisition and Reconnaissance - and it resolves to a real
company called iStar Inc. Our acronym rule catches pluralised acronyms like
"ASICs" but not this.

**Q36. What is your largest remaining failure class?**
Entity resolution, 6 of the 19 narrative failures. The right relationship bound
to the wrong legal entity - "Carraro S.p.A." resolving to Carraro India Limited,
"Hyundai" to Hyundai Motor India rather than Hyundai Motor Company.

**Q37. Why not just fix those?**
Because deciding which Hyundai a sentence means needs context the sentence does
not contain. The honest options are a model with world knowledge, or suppressing
ambiguous aliases and losing the relationship entirely. We chose to measure the
problem rather than hide it.

---

## 5. How extraction actually works

**Q38. Walk me through the pipeline.**
Fetch filings from EDGAR. Segment into Items. Chunk. Stage one gates chunks on
cheap lexicon matches. Stage two reads surviving sentences and emits claims.
Claims that are resolved, named and real get promoted to edges. Then events
propagate across the graph.

**Q39. What is stage one for?**
Cost. Two thirds of chunks contain a dependency cue at all; the rest can be
dropped without reading them properly. If stage two were a paid model call, this
is what makes the bill finite.

**Q40. How much does stage one actually save?**
It passed 9,829 of 14,738 chunks, so 33% dropped at essentially zero cost. The
earlier text-level measurement was an 85% reduction in characters reaching the
expensive stage.

**Q41. Why not send whole documents to a model?**
Cost and citation. A whole-document call cannot tell you which sentence a claim
came from, and the citation guarantee is the product.

**Q42. How do you find company names in text?**
A gazetteer of aliases, matched as token n-grams longest-first, with case
preserved.

**Q43. Why does case matter?**
It is the strongest signal in the text and we were throwing it away. We used to
uppercase everything before matching, so "financial institutions" matched a
company named Financial Institutions, and "coats" - the verb - matched Coats
Group.

**Q44. How do you tell a generic phrase from a real company name, when both are
ordinary English?**
We measure it rather than guess. A company name is written capitalised nearly
every time it appears; a generic phrase is not. So we count both forms across
all 225 filings and keep only names that are overwhelmingly capitalised.

**Q45. Does that actually work?**
Yes, cleanly. Nasdaq appeared in 53% of filings and Sarbanes-**Oxley** in 59% -
both removed. "Wearable Devices" was lowercase in 12 of 12 occurrences -
removed. Boeing, Stellantis, FedEx and Applied Materials all kept. The full
audit table is `eval/gazetteer_df.tsv`.

**Q46. Why not just use a dictionary of English words?**
We tried. `/usr/share/dict/words` is Webster's Second and has no plurals, so
"Commodities", "Institutions" and "Investments" all sailed through. And a
dictionary cannot help you at all with "Applied Materials", where both words are
ordinary English and the company is real.

**Q47. How do you decide if a counterparty is a supplier or a customer?**
From the grammar around the cue word, not the cue word alone. "We are a supplier
to Ford" and "our suppliers include Ford" use the same noun and point in
opposite directions.

**Q48. What happened when you got that wrong?**
Roughly a third of the graph pointed the wrong way. Adient's filing says "Adient
is a supplier to ... BMW, Mercedes-Benz", and we read it as Adient depending on
BMW. It is exactly backwards.

**Q49. Give me other things that look like dependencies but are not.**
Executive biographies - "Mr. Nolan served as President of Avery Dennison".
Social media accounts. Search engines. Competitor lists. Share buybacks. The
company's own plants and brands - "our Hopewell plant", "Metro(R) vehicles". All
are filtered explicitly now.

**Q50. How do you split sentences? Filings are full of abbreviations.**
We find candidate boundaries on punctuation followed by whitespace and a
capital, then drop any boundary that follows a known abbreviation - Inc., Corp.,
Ltd. and so on.

---

## 6. Point-in-time correctness

**Q51. What is look-ahead bias?**
Using information to explain or predict an event when that information was not
public at the time of the event. It is the single easiest way to produce a
backtest that looks brilliant and is worthless.

**Q52. How do you prevent it?**
Every edge carries `valid_from`, set to the filing date. Every read goes through
`edges_as_of(timestamp)`, which returns only edges whose source document was
already public at that moment.

**Q53. Why one read path instead of filtering at each call site?**
Because a filter you have to remember is a filter you will forget. One function
means one place to get it right.

**Q54. Show me that it actually works.**
Replay the Ever Given event, March 2021. The graph returns zero exposed
companies, because every filing we hold was published after that date. The UI
says so explicitly rather than showing an empty list. That is the rule working,
not a gap in the data.

**Q55. That makes your demo look broken.**
It makes it look honest. An examiner who sees a 2021 event light up a graph
built from 2025 filings should fail us, and would be right to.

---

## 7. Propagation

**Q56. What happens when you simulate an event?**
We seed the companies directly affected, then walk the graph outward up to three
hops, multiplying by a decay factor of 0.55 at each hop.

**Q57. Why three hops?**
Beyond three the signal is weaker than the noise in our own precision. With 68%
precision on narrative edges, a three-hop path is three uncertain steps
compounded. Four would be indefensible.

**Q58. Why 0.55?**
It is a chosen constant, not a fitted one, and we will say so. We have no ground
truth to fit it against. It is versioned in `scorer_version` so any change is
traceable.

**Q59. What does "surprising" mean in your UI?**
A company at two or more hops from the event. At one hop you would have thought
of them yourself. At two or three you would not have, and that is the whole
value proposition.

**Q60. Does the walk ever cycle?**
No. It is bounded by hop count and visits each node once per event, so it
terminates deterministically.

**Q61. Your Hormuz event shows 102 exposed companies. Is that real?**
It is a real walk over real cited edges. Whether 102 companies would genuinely
suffer is a modelling claim we do not make - we say they are connected by
disclosed dependencies, and we show the sentences.

---

## 8. Data and coverage

**Q62. How many companies do you cover?**
23,020 entities loaded from seven markets. 79 of them currently have cited
edges, from 225 filings.

**Q63. That's a tiny fraction.**
Yes. The entity universe is the addressable set; the graph is what we have
actually read. We have never presented those as the same number and we will not
start now.

**Q64. Which markets?**
US NASDAQ, US NYSE, India, UK, Germany, Canada, Australia.

**Q65. Why does the graph only cover US filings then?**
Because EDGAR is a free, machine-readable, full-text API and the other
regulators are not. Expanding means per-regulator ingestion work, not a change
in method.

**Q66. How do you handle a company listed on two exchanges?**
One entity, many listings. `entity_listing` holds the listings and the entity
holds the identity, so a dual-listed company is not two nodes in the graph.

**Q67. Where does your geographic data come from?**
GeoNames under CC BY 4.0 and an MIT-licensed US cities dataset. Both permit
redistribution, which matters because we redistribute.

**Q68. Why don't you use GICS sectors?**
GICS is licensed and we cannot redistribute it. We built our own sector mapping.
A reviewer asking why our sectors are not GICS is really asking whether we
understood the licensing, and we did.

**Q69. You have CUSIP and SEDOL identifiers. Are you publishing them?**
No. They are withheld at the API layer. They are licensed identifiers, and
storing them for internal joins is not the same as redistributing them.

**Q70. Why did you turn down licensed transcript data?**
Because the licence terms would have forbidden us from republishing the source
sentence. That breaks the citation guarantee, which is the entire product. The
cheaper data was not worth the thing that makes us different.

---

## 9. Architecture and engineering

**Q71. Why PostgreSQL rather than a graph database?**
Our graph is small and our queries are shallow - three hops, bounded. Postgres
gives us transactions, constraints, row-level security and PostGIS in one
system. A graph database would have bought traversal speed we do not need and
cost us constraints we do.

**Q72. Will that scale?**
To the size this problem has, yes. The bound on the graph is how many filings
disclose named counterparties, which is thousands of edges, not billions. If we
were wrong about that, the read path is one function and could be backed by
something else.

**Q73. Why row-level security from the first migration?**
Because retrofitting tenancy is a rewrite. It cost us very little on day one and
would have cost a great deal on day two hundred.

**Q74. How fast is the API?**
5 ms median against a 200 ms budget, because exposure is precomputed rather than
walked at request time.

**Q75. Why precompute?**
The walk is deterministic and the inputs change only when we ingest. There is no
reason to recompute the same answer on every request.

**Q76. What is the frontend?**
React and TypeScript, with a WebGL globe via react-globe.gl on three.js.

**Q77. Why a globe at all? Isn't it decoration?**
Partly, and we should be honest about that. It earns its place because
dependency and geography interact - a strait, a fab, a fire all have locations -
and because it makes a two-hop surprise visible as an arc rather than a table
row.

**Q78. How do you keep the API and the UI types in sync?**
A shared TypeScript package of API types. The UI cannot read a field the
contract does not declare.

---

## 10. Product and ethics

**Q79. Do you tell people what to buy?**
No. Not one recommendation anywhere in the system.

**Q80. Why not? That's where the money is.**
Because a recommendation makes us liable in a way an evidence trail does not,
and because we have no basis for one. We have 68% precision on narrative edges.
Telling someone to sell on that would be indefensible.

**Q81. But the brief mentions buy/sell/IPO guidance.**
And the answer we give is the same: Atlas surfaces disclosed dependency and the
evidence for it. What a user does with that is their decision and their
responsibility. We can show that Ducommun depends on Boeing for 13% of revenue
and cite it. We will not tell anyone to sell Ducommun.

**Q82. Is any of this insider information?**
No. Every byte is from public regulatory filings, fetched by our own code on our
own accounts. No employer systems, no exports, no credentials, no licensed
feeds.

**Q83. What is the clean-room rule?**
That the only thing any of us brings from outside is knowledge, not data. It is
written down because a project like this is exactly where that line gets blurred
without anyone deciding to blur it.

**Q84. Could this be used to manipulate a market?**
It republishes what companies already disclosed, with pointers to where they
disclosed it. If anything it reduces information asymmetry. The risk we take
seriously is the opposite one - someone trusting a 68% edge as if it were 100%,
which is why the UI labels the tiers.

**Q85. What is the single biggest risk to the product?**
That someone acts on a wrong edge. Our mitigations are the citation on every
edge, the measured precision published alongside it, and the visible distinction
between disclosed-percentage and named-only evidence.

---

## 11. Questions about us

**Q86. What did you personally build?**
Answer with your own area and be specific about a problem you solved. Do not
claim the whole system. An examiner can tell within two follow-up questions.

**Q87. What was the hardest bug?**
Good answers from this project: the gazetteer matching "OPERA" inside
"OPERATIONS"; percentage attribution copying one customer's share to every name
in a table; the direction inversion that pointed a third of the graph backwards.

**Q88. What would you do differently?**
Measure earlier. We built the whole pipeline before auditing a single edge, and
the audit changed our understanding of our own system more than any feature did.

**Q89. What did you learn that you did not expect?**
That the most valuable work was deleting edges, not adding them. We went from
803 edges to 194 relationships and the system got substantially better.

**Q90. What is next?**
Measure recall. Swap stage two for a schema-forced model call and re-measure
against the same samples. Fix entity resolution for ambiguous aliases. Extend
ingestion past EDGAR.

**Q91. If I gave you three more months, what would you have?**
A recall number, a model-backed stage two with a measured delta against these
exact samples, and a second regulator ingested. Not more features.

---

## 12. Traps

**Q92. "So the AI reads the filings and builds the graph?"**
Careful. The model reads one sentence at a time and returns structure. It does
not build the graph and it does not score anything. Correct the framing, politely.

**Q93. "Your accuracy is 72%, so about a quarter of your graph is wrong?"**
Roughly, for the narrative tier, and we publish that. The concentration tier,
which is what the product leads with, measured 26 of 26 correct.

**Q94. "Why should I believe your evaluation?"**
Because the sample file, the seed, and every cited sentence are in the repo. You
can re-judge our sample and tell us we were wrong.

**Q95. "Couldn't you have just used an LLM for all of this?"**
For stage two, yes, and that is the design. Not for scoring, not for the
citation, and not for point-in-time correctness - those must be deterministic or
the product has no integrity.

**Q96. "This is just a wrapper around SEC data."**
It is a method for inverting a deliberate information asymmetry, plus an
evaluated extraction pipeline, plus a point-in-time correct read path. The data
is public. So is the dictionary, and that did not make writing one easy.

**Q97. "What happens when the SEC changes its format?"**
Ingestion breaks and we fix it. That is true of every system that reads a
regulator's output, which is why segmentation is isolated in `ingest.py` rather
than spread through the pipeline.

**Q98. "Can I see an edge you know is wrong?"**
Yes - and say yes. Broadcom to VMware. Then explain why it is wrong and why no
sentence-level rule can fix it. Volunteering a known failure is worth more than
defending a perfect record nobody believes.

---

## The three sentences to have ready

1. **What it is.** A graph of which public companies depend on which, built
   bottom-up from small suppliers' mandatory disclosures, where every edge cites
   the sentence that proves it.

2. **Why it is hard.** Large buyers never publish their suppliers, so the only
   way in is from the other end, where disclosure is compulsory.

3. **How good it is.** 26 of 26 correct where a percentage is disclosed; 68% on
   a random sample where the filing only names a counterparty; and we can show
   you the sentences for both.
