# Superseded decisions

Decisions that were seriously held, then changed. Kept because "why didn't you do X?"
should be answerable from the repo, and because the reasoning that moved us is usually
more interesting than the conclusion.

---

## The customer digital twin as the data model

**Held:** 26–27 August 2026, in `docs/PROBLEM-STATEMENT.md`, `ROADMAP.md` and `ARCHITECTURE.md`.
**Superseded:** 20 September 2026. Agreed by all five.

### What it was

A customer — a procurement manager at a mid-size Indian manufacturer, an operations head
at an exporter, an account manager at a freight forwarder — uploads their own reality:
suppliers, origin and destination ports, lanes, SKUs, input commodities. We build that
into a graph, and world events propagate through **their** graph rather than a generic one.
Value is private to the customer and compounds the longer they use it.

### Why it moved

The twin was never the data asset. **It was the delivery surface**, and we had the two
confused.

A procurement manager who types in forty suppliers learns nothing from us, because they
already know their tier-1 — they typed it in. The thing they cannot type in is the thing
they need: who their suppliers depend on, and who those companies depend on. Tier-2 and
tier-3 is precisely the knowledge that is absent from a customer's own records, which is
why a product built entirely on customer-supplied data has nothing to add to it.

So the graph has to come from somewhere other than the customer. It comes from public
disclosure, built bottom-up from the smaller side, because small suppliers name their
large customers while large customers hide their small suppliers.

### What survived

Almost everything except the data model.

- **The user survives as the buyer.** Procurement, credit and trade-credit insurance
  remain the wedge. See `STARTUP/wedge.md`.
- **The twin survives as a Phase 5+ feature, "bring your own tier-1."** The customer
  uploads their supplier list, we resolve those names against the public graph, and we
  return the two hops they could not have typed. This is also the commercial answer to
  "why would they pay." See [`STARTUP/business-model.md`](STARTUP/business-model.md).
- **Replay and simulation survive unchanged**, and get considerably better, because a
  public graph can be reconstructed as it stood on a past date while a customer's
  uploaded spreadsheet cannot.
- **The refusal to build a trading product survives**, along with its reasoning, now in
  [`COMPLIANCE.md`](COMPLIANCE.md).
- **`DESIGN.md`, `TEAM.md` and the non-negotiables in `ARCHITECTURE.md` survive as written.**

### What it cost us

The twin had one genuine advantage we have given up: no cold start. A customer's uploaded
supplier list is dense and correct on day one, while a disclosure graph has to be built
before anyone can use it, and it will be sparse in places no matter how well we build it.

We are accepting a harder cold start in exchange for an asset that exists independently of
any single customer, compounds across all of them, and can be shown to a prospect before
they have given us anything.

---

## The `reference/` folder

`reference/` holds a captured copy of a third party's deployed product (web-code.tech /
"GeoTrade"), studied before starting. Its rules are unchanged and still binding — see
[`../reference/DO-NOT-SHIP.md`](../reference/DO-NOT-SHIP.md). Nothing from it ships. What
we took was the observation that a globe is a good primary view, and a clear picture of
the generated-dashboard house style we are deliberately avoiding, catalogued in `DESIGN.md`.
