# Design direction — how to not look AI-generated

## What "AI-made" actually looks like

There is a house style that every generated dashboard converges on, and everyone
recognises it now:

- Dark navy or near-black background, `#0a0e1a`-ish
- A purple→blue or cyan gradient, usually on the headline
- Glassmorphism cards: translucent, blurred, 1px white border at 10% opacity
- Inter or Space Grotesk, one weight, generously spaced
- Everything glowing faintly
- Rounded-2xl on every corner
- Big empty hero, four stat cards in a row, a chart, a table
- Copy that says "Powered by AI" and "real-time insights"

The reference project in `../reference/` has essentially all of these. That is why it
reads as generated. **Every one of these is banned in our repo.** If a PR contains a
purple gradient on a dark navy card, it gets rejected on sight.

## Pick a real direction instead

The design should come from somewhere — a discipline, an era, a physical object.
Three that fit a supply-chain product, all of them unusual on a screen:

### A. Nautical chart *(recommended)*

Admiralty sea charts: warm paper cream, fine black hairlines, depth soundings as tiny
numerals, rhumb lines radiating from compass roses, hand-lettered place names, one red
accent for hazards. Dense, technical, beautiful, and nobody's AI-generated dashboard
looks like this. It also *means* something for a product about shipping lanes.

Globe treatment: dark ocean, thin luminous lane lines, ports as small precise circles
with hairline leaders to labels. Restrained, not glowing.

### B. Flight-operations panel

Boeing/Airbus cockpit and airline ops centres: near-black, amber and green phosphor,
monospace numerals, hard edges, zero decoration, extremely high information density.
Reads as serious infrastructure.

### C. Swiss editorial / scientific report

White, huge type scale contrast, a strict grid, black rules, one accent. Looks like a
research institution published it. Very strong for the thesis and the credibility of
the numbers.

**Decide in week 1, as a team, and write the choice at the bottom of this file.**
A consistent mediocre direction beats an inconsistent brilliant one.

## Rules regardless of direction

1. **Type: two families, real hierarchy.** One for interface, one for numerals
   (tabular figures — numbers must line up in columns). Buy or use a distinctive open
   face; avoid the defaults everyone ships.
2. **Colour: one accent, used rarely.** If everything is highlighted, nothing is. The
   accent means "look here now," and appears maybe three times per screen.
3. **Density is a feature.** Real operators want more on screen, not less. Bloomberg,
   flight ops, and trading desks are dense because dense is useful. Resist the urge to
   make it airy — airy reads as "no data behind it."
4. **Motion must mean something.** Animate to show causality — an event propagating
   along a lane. Never animate for decoration. No floating particles.
5. **Empty states, loading states, error states are designed**, not afterthoughts.
   This is the single clearest tell between student work and product work.
6. **Write like a person.** "Your Ningbo shipments cross Suez" beats "AI-powered
   real-time geopolitical intelligence." Never use the words *seamless*, *leverage*,
   *revolutionise*, or *cutting-edge* in the UI.
7. **Draw it in Figma first.** Code is a bad place to explore visual ideas, and the
   frontend owner should not be inventing the design at 2am inside a component.

## The globe specifically

We keep a 3D globe because it genuinely fits — the product is about distance, routes
and chokepoints — and because it is the best thing on screen. But it must earn it:

- The globe answers a question ("where is my exposure"), it is not a screensaver
- Clicking a country, lane or port goes somewhere useful
- There is a 2D map view for people who need to actually read the geography
- It never blocks the data. If the globe is loading, the numbers are already there

Build it ourselves with `react-globe.gl` (MIT). Our textures, our colour treatment,
our interaction model.

---

**Direction chosen by the team:** _______________  **Date:** __________
