#!/usr/bin/env python3
"""Record the full explainer: animated deck -> live app -> closing slides.

    python3 -I scripts/narrate.py      # generate the voice track (optional)
    python3 -I scripts/record_demo.py  # record and mux

One continuous take in one browser. The app section drives the real app against the
real API and database, so if the app is broken the video is broken - that is the point.

The narration below is the single source of truth: narrate.py speaks these exact lines
and the app section prints the same text as its caption, so voice and subtitle cannot
drift apart.
"""
import json, os, pathlib, shutil, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB  = os.environ.get("ATLAS_WEB", "http://localhost:5173")
# as_uri() percent-encodes; the project path contains spaces.
DECK = pathlib.Path(ROOT, "demo/presentation/index.html").as_uri()
OUT  = os.path.join(ROOT, os.environ.get("ATLAS_DEMO_OUT", "demo"))
W, H = 1600, 1000

# key, scene-or-None, spoken text.  scene != None -> show that deck slide.
NARRATION = [
 ("title", "title",
  "Atlas. A map of which public companies depend on which others, built only from what "
  "those companies have already said in public."),
 ("problem", "problem",
  "When something happens in the world — a port closes, a plant burns, a country restricts "
  "an export — the companies hit first are obvious. Any analyst already has those names."),
 ("hidden", "hidden",
  "The companies hit third are not obvious. They buy from the companies that got hit, and "
  "nobody keeps a list of them. That gap is the whole product."),
 ("why_hard", "why-hard",
  "The obvious way to build that list is to read large companies' filings and extract their "
  "suppliers. It does not work. Supplier identities are commercially sensitive, so they are "
  "written out of the document on purpose."),
 ("inversion", "inversion",
  "So we build the graph from the other end. Large companies hide their suppliers, but small "
  "suppliers advertise their large customers, because a marquee customer is their best "
  "credential. The edge you cannot get from the buyer, you get free from the seller."),
 ("measured", "measured",
  "We measured that before building on it. A zero-cost keyword pass over ten real "
  "semiconductor filings surfaced Lam Research and Applied Materials six times each in one "
  "supplier's annual report. No model involved."),
 ("rules", "rules",
  "Three rules keep it honest, and all three are enforced in the database schema rather than "
  "in code review. Every edge carries its citation. The model never produces a score. And "
  "the graph knows what it knew on any given date."),
 ("pipeline", "pipeline",
  "The pipeline takes prose in and puts cited claims out. Fetch, segment, chunk, filter, "
  "extract, resolve, score. Only the extract step uses a model, and only on fifteen percent "
  "of each document."),
 ("tothe_app", "tothe-app",
  "The data layer is built and running today. Twenty-three thousand companies across six "
  "markets. Let us look at it."),

 # ---- live app ----
 ("coverage", None,
  "This is the real application, reading a live Postgres database. Every bar is a company "
  "headquarters, binned by density. Coverage by country is counted from the data."),
 ("sectors", None,
  "Pick a country and the sectors are counted from the database, not read from a hardcoded list."),
 ("companies", None,
  "Semiconductors — the sector where small suppliers name their large customers. "
  "Real companies, with real identifiers behind each one."),
 ("company", None,
  "Legal name, sector, headquarters, identifiers, former names. Former names matter, because "
  "an old filing uses the old name, and missing that splits one company into two."),
 ("replay", None,
  "Now the part that matters. Replay a real disruption."),
 ("arcs", None,
  "An event in the Taiwan Strait. The arcs are the dependency chain reaching outward — across "
  "the Pacific, and down into India."),
 ("surprise", None,
  "The marked names are the ones you would not have listed yourself. Five of the seven here "
  "are two or three hops out from the event."),
 ("citation", None,
  "And each hop carries the exact sentence that proves it. If we cannot show you the sentence, "
  "we do not make the claim."),
 ("backtest", None,
  "The timeline is the backtest. Scrub to any past disruption and the graph is read as it "
  "stood that morning, never with anything filed later. That is what stops a backtest from "
  "quietly cheating."),
 ("honest", None,
  "And we are explicit about what is not built yet. Extraction has not run, so these edges are "
  "a worked example, and the application says so on screen rather than implying coverage it "
  "does not have."),

 # ---- closing slides ----
 ("where", "where",
  "Twenty weeks, six phases, each ending in something that runs. This is the end of the data "
  "layer. Week three is a validation experiment before any pipeline is built on top of it — "
  "forty documents, two annotators each, with the decision rules written down before anybody "
  "reads one."),
 ("close", "close",
  "Every claim traces to a sentence. Every score is code you can read. And the graph knows "
  "what it knew, and when."),
]
TEXT = {k: t for k, _s, t in NARRATION}
SCENE = {k: s for k, s, _t in NARRATION}

CURSOR_AND_CAPTION = """
(() => {
  // add_init_script runs before <body> exists, so everything here is deferred.
  let dot, ring, cap;
  function build() {
    if (cap || !document.body) return;
    dot = document.createElement('div');
    dot.style.cssText = `position:fixed;z-index:99999;width:18px;height:18px;margin:-9px 0 0 -9px;
      border-radius:50%;border:2px solid #b8372a;background:rgba(184,55,42,.22);
      pointer-events:none;transition:transform .08s linear;left:-100px;top:-100px;`;
    ring = document.createElement('div');
    ring.style.cssText = `position:fixed;z-index:99998;width:46px;height:46px;margin:-23px 0 0 -23px;
      border-radius:50%;border:2px solid #b8372a;opacity:0;pointer-events:none;left:-100px;top:-100px;`;
    cap = document.createElement('div');
    cap.style.cssText = `position:fixed;z-index:99999;left:0;right:0;bottom:0;padding:18px 30px;
      background:rgba(20,19,14,.94);color:#f2ece0;font:400 20px/1.45 ui-serif,Georgia,serif;
      opacity:0;transition:opacity .35s ease;pointer-events:none;border-top:2px solid #b8372a;`;
    document.body.append(dot, ring, cap);
    addEventListener('mousemove', e => {
      dot.style.left = ring.style.left = e.clientX + 'px';
      dot.style.top  = ring.style.top  = e.clientY + 'px';
    }, true);
    addEventListener('mousedown', () => {
      dot.style.transform = 'scale(.65)';
      ring.style.transition = 'none'; ring.style.opacity = '.9'; ring.style.transform = 'scale(.5)';
      requestAnimationFrame(() => {
        ring.style.transition = 'transform .45s ease-out, opacity .45s ease-out';
        ring.style.opacity = '0'; ring.style.transform = 'scale(1.25)';
      });
    }, true);
    addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
  }
  window.__say = t => {
    build();
    if (!cap) return;
    if (!t) { cap.style.opacity = '0'; return; }
    cap.textContent = t; cap.style.opacity = '1';
  };
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', build);
  else build();
})();
"""

def main():
    os.makedirs(OUT, exist_ok=True)
    raw = os.path.join(OUT, "raw")
    shutil.rmtree(raw, ignore_errors=True)
    os.makedirs(raw, exist_ok=True)

    spoken = {}
    spath = os.path.join(OUT, "narration", "script.json")
    if os.path.exists(spath):
        spoken = {x["key"]: x for x in json.load(open(spath))["lines"]}
        print(f"  narration: {len(spoken)} lines, "
              f"{sum(x['duration'] for x in spoken.values()):.0f}s of speech")
    else:
        print("  narration: none — run scripts/narrate.py first for voice-over")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--force-device-scale-factor=1", "--hide-scrollbars",
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            "--ignore-gpu-blocklist", "--enable-gpu-rasterization"])
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  record_video_dir=raw,
                                  record_video_size={"width": W, "height": H},
                                  device_scale_factor=1)
        page = ctx.new_page()
        page.add_init_script(CURSOR_AND_CAPTION)

        t0 = time.monotonic()
        timings, hold = [], [0.0]

        def now(): return time.monotonic() - t0

        def beat(s=1.0):
            """Wait the written beat, or until the narration for the current line has
            finished — whichever is longer. The video paces itself to the voice."""
            target = max(now() + s, hold[0])
            while True:
                left = target - now()
                if left <= 0: return
                page.wait_for_timeout(int(min(left, 0.4) * 1000))

        def line(key, caption=True, pad=0.5):
            text = TEXT[key]
            if caption:
                page.evaluate("t => window.__say(t)", text)
            start = now()
            timings.append({"key": key, "start": round(start, 3)})
            if key in spoken:
                hold[0] = start + spoken[key]["duration"] + pad
            print(f"    [{start:6.1f}s] {key}")

        def scene(key):
            page.evaluate("k => window.__scene(k)", SCENE[key])

        def glide(x, y, steps=26): page.mouse.move(x, y, steps=steps)

        # ================= deck: the explanation =================
        page.goto(DECK, wait_until="load")
        page.wait_for_function("() => !!window.__scene", timeout=15000)
        beat(1.0)
        for k in ("title", "problem", "hidden", "why_hard", "inversion",
                  "measured", "rules", "pipeline", "tothe_app"):
            scene(k); line(k, caption=False); beat(1.6)
        beat(0.8)

        # ================= the live application =================
        page.goto(WEB, wait_until="networkidle")
        page.wait_for_selector("canvas", timeout=30000)
        page.wait_for_selector('button.row-country', timeout=30000)
        page.wait_for_timeout(5000)      # globe builds and starts rotating
        glide(W * 0.40, H * 0.5, steps=1)
        beat(0.8)

        line("coverage")
        box = page.evaluate("""() => {
          const r = document.querySelector('canvas').getBoundingClientRect();
          return { x: r.x, y: r.y, w: r.width, h: r.height };
        }""")
        cx, cy = box["x"] + box["w"] * 0.44, box["y"] + box["h"] * 0.46
        glide(cx, cy)
        page.mouse.down()
        for dx in range(0, 150, 10):
            page.mouse.move(cx + dx, cy - dx * 0.16); page.wait_for_timeout(18)
        page.mouse.up()
        beat(1.4)

        # Click the country in the panel, not on the sphere: a moving 3D target is a
        # bad thing to aim a demo at, and the list is the better affordance anyway.
        row = page.locator("button.row-country").first
        b = row.bounding_box()
        if b: glide(b["x"] + 150, b["y"] + b["height"] / 2)
        beat(0.6); row.click(); beat(2.4)

        line("sectors"); beat(1.6)

        want = page.get_by_role("button", name="Semiconductor Devices")
        rows = want if want.count() else page.locator("button.row-sector")
        if rows.count():
            r0 = rows.first
            r0.scroll_into_view_if_needed()
            b = r0.bounding_box()
            if b: glide(b["x"] + 140, b["y"] + b["height"] / 2)
            beat(0.6); r0.click(); beat(2.2)
            line("companies"); beat(1.6)
            crow = page.locator("button.row-company")
            if crow.count():
                b = crow.first.bounding_box()
                if b: glide(b["x"] + 140, b["y"] + b["height"] / 2)
                beat(0.5); crow.first.click(); beat(2.4)
                line("company"); beat(1.6)

        line("replay")
        rep = page.get_by_role("button", name="replay")
        b = rep.bounding_box()
        if b: glide(b["x"] + 30, b["y"] + b["height"] / 2)
        beat(0.8); rep.click(); beat(3.4)

        line("arcs");     beat(1.8)
        line("surprise"); beat(1.6)
        line("citation"); page.mouse.wheel(0, 300); beat(1.8)

        line("backtest")
        page.mouse.wheel(0, -400)
        pips = page.locator("button.tl-pip")
        # The 2021 pips sit weeks apart and overlap, so they intercept each other's
        # clicks. Pick a well-separated one and force past the hit-testing.
        if pips.count() >= 5:
            b = pips.nth(4).bounding_box()
            if b: glide(b["x"] + b["width"] / 2, b["y"] + 6)
            beat(0.8); pips.nth(4).click(force=True)
        beat(2.4)

        line("honest"); beat(2.0)
        page.evaluate("() => window.__say(null)"); beat(0.8)

        # ================= deck: where this goes =================
        page.goto(DECK, wait_until="load")
        page.wait_for_function("() => !!window.__scene", timeout=15000)
        beat(0.6)
        for k in ("where", "close"):
            scene(k); line(k, caption=False); beat(2.0)
        beat(1.6)

        ctx.close(); browser.close()

    webm = next((os.path.join(raw, f) for f in os.listdir(raw) if f.endswith(".webm")), None)
    if not webm: sys.exit("no video produced")
    ndir = os.path.join(OUT, "narration")
    os.makedirs(ndir, exist_ok=True)
    json.dump({"timings": timings}, open(os.path.join(ndir, "timings.json"), "w"), indent=1)

    silent = os.path.join(OUT, "atlas-demo-silent.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", webm,
                    "-vf", "scale=1600:-2:flags=lanczos,fps=30",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent], check=True)

    final = os.path.join(OUT, "atlas-demo.mp4")
    if spoken and mux(silent, timings, spoken, final):
        os.remove(silent)
    else:
        shutil.move(silent, final)

    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "4", "-t", "14", "-i", final,
                    "-an", "-vf", "fps=12,scale=720:-2:flags=lanczos,split[a][b];"
                    "[a]palettegen=max_colors=128[p];[b][p]paletteuse",
                    os.path.join(OUT, "atlas-demo.gif")], check=False)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", final],
                         capture_output=True, text=True).stdout.strip()
    print(f"\n  {final}  {os.path.getsize(final)/1e6:.1f} MB  {float(dur):.0f}s")


def mux(video, timings, spoken, out):
    """Lay each spoken line back over the video at the moment its caption appeared."""
    clips = [(t["start"], spoken[t["key"]]["wav"]) for t in timings
             if t["key"] in spoken and os.path.exists(spoken[t["key"]]["wav"])]
    if not clips:
        return False
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video]
    for _s, w in clips: cmd += ["-i", w]
    parts, labels = [], []
    for i, (start, _w) in enumerate(clips, start=1):
        ms = max(0, int(start * 1000))
        parts.append(f"[{i}:a]adelay={ms}|{ms},volume=1.0[a{i}]")
        labels.append(f"[a{i}]")
    # normalize=0 keeps each line at full level instead of dividing by input count
    parts.append("".join(labels) + f"amix=inputs={len(clips)}:normalize=0:dropout_transition=0[mix]")
    parts.append("[mix]aresample=48000,alimiter=limit=0.95[a]")
    cmd += ["-filter_complex", ";".join(parts),
            "-map", "0:v", "-map", "[a]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k", "-shortest", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("  mux failed:", r.stderr.strip()[:400]); return False
    print(f"  muxed {len(clips)} narration lines")
    return True


if __name__ == "__main__":
    main()
