"""Generate animated, isometric README SVGs from the sample network CSVs.

usage: python docs/tools/gen_svgs.py   (writes docs/images/hero-3d.svg, stats.svg, pipeline.svg)
The hero panel figures are the F1 scenario from docs/twin-data.js (regenerate with export_twin.py first).
"""
import csv, math, sys, os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "docs", "images")

nodes = list(csv.DictReader(open(os.path.join(ROOT, "backend/mock/sample_nodes.csv"))))
edges = list(csv.DictReader(open(os.path.join(ROOT, "backend/mock/sample_edges.csv"))))
N = {n["id"]: n for n in nodes}

COL = {  # top, left side, right side
    "supplier": ("#a78bfa", "#6d48d8", "#5636b0"),
    "factory": ("#60a5fa", "#2563eb", "#1d4ccc"),
    "warehouse": ("#2dd4bf", "#0d9488", "#0a7068"),
    "customer": ("#94a3b8", "#526077", "#3b465a"),
}
SIDES = {"supplier": 3, "factory": 4, "warehouse": 6, "customer": 14}
RAD = {"supplier": 9, "factory": 12, "warehouse": 15, "customer": 8}

W, H = 1280, 640
CX, CY, S = 400, 345, 22.0
C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))


def iso(x, y, h=0.0):
    return CX + (x - y) * C30 * S, CY + (x + y) * S30 * S - h


def plane(lon, lat):
    # rotate 45 deg so north points up the screen in the isometric view
    e, n = lon - 80.0, lat - 22.0
    return (e - n) / math.sqrt(2), (-e - n) / math.sqrt(2)


INDIA = [(68.1, 23.6), (69.5, 24.3), (71.0, 24.4), (70.6, 25.7), (70.0, 26.6), (71.0, 27.8), (72.4, 28.9),
         (73.4, 29.9), (74.5, 31.0), (74.6, 32.5), (74.0, 33.5), (74.3, 34.7), (76.0, 35.4), (77.8, 35.4),
         (78.9, 34.3), (78.7, 32.6), (79.0, 31.3), (80.3, 30.5), (81.1, 30.0), (82.0, 28.8), (83.3, 27.4),
         (84.6, 27.3), (86.0, 26.6), (88.1, 26.5), (88.8, 27.3), (89.8, 26.7), (92.0, 26.9), (93.8, 27.6),
         (95.4, 28.3), (97.3, 28.2), (96.0, 27.0), (95.1, 26.0), (94.6, 25.2), (94.1, 23.9), (93.3, 24.0),
         (92.6, 22.0), (92.2, 23.6), (91.4, 24.1), (90.2, 25.2), (89.0, 25.2), (88.7, 24.3), (88.9, 22.0),
         (88.0, 21.6), (86.9, 21.4), (85.1, 19.5), (84.0, 18.3), (82.3, 16.6), (80.3, 15.6), (80.2, 13.4),
         (79.9, 10.3), (78.9, 9.0), (77.5, 8.1), (76.5, 8.9), (75.8, 11.3), (74.8, 12.9), (74.1, 14.8),
         (73.5, 16.0), (72.9, 18.9), (72.6, 21.1), (72.5, 22.4), (70.0, 20.8), (69.0, 22.3)]


def pts(seq):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in seq)


def prism(nid):
    n = N[nid]
    kind = n["kind"]
    px, py = plane(float(n["lon"]), float(n["lat"]))
    h = 18 + float(n["stock"]) / 2200 * 70
    if kind == "factory":
        h += 10
    k, r = SIDES[kind], RAD[kind] / S
    rot = math.pi / k if kind != "factory" else math.pi / 4
    ring = [(px + r * math.cos(rot + 2 * math.pi * i / k), py + r * math.sin(rot + 2 * math.pi * i / k)) for i in range(k)]
    top, left, right = COL[kind]
    base = [iso(x, y) for x, y in ring]
    up = [iso(x, y, h) for x, y in ring]
    out = []
    faces = []
    for i in range(k):
        j = (i + 1) % k
        (x0, y0), (x1, y1) = ring[i], ring[j]
        # outward normal in plane; viewer looks along (+1,+1)
        nx, ny = (y1 - y0), -(x1 - x0)
        facing = nx + ny
        if facing <= 0:
            continue
        shade = right if nx > ny else left
        depth = (x0 + x1 + y0 + y1)
        faces.append((depth, f'<polygon points="{pts([base[i], base[j], up[j], up[i]])}" fill="{shade}"/>'))
    for _, f in sorted(faces):
        out.append(f)
    out.append(f'<polygon points="{pts(up)}" fill="{top}"/>')
    if kind == "factory":  # chimney stack
        sx, sy = px + r * 0.35, py - r * 0.35
        sr = r * 0.28
        sq = [(sx - sr, sy - sr), (sx + sr, sy - sr), (sx + sr, sy + sr), (sx - sr, sy + sr)]
        b2 = [iso(x, y, h) for x, y in sq]
        u2 = [iso(x, y, h + 16) for x, y in sq]
        out.append(f'<polygon points="{pts([b2[1], b2[2], u2[2], u2[1]])}" fill="{right}"/>')
        out.append(f'<polygon points="{pts([b2[2], b2[3], u2[3], u2[2]])}" fill="{left}"/>')
        out.append(f'<polygon points="{pts(u2)}" fill="{top}"/>')
    tx, ty = iso(px, py, h)
    bx, by = iso(px, py)
    return "\n".join(out), (tx, ty), (bx, by), py + px


def hero():
    g = []
    g.append(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Animated isometric view of the AEGIS digital twin: factory F1 shuts for 10 days and the failure ripples downstream">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#05070f"/><stop offset=".6" stop-color="#0c1230"/><stop offset="1" stop-color="#170f3a"/></linearGradient>
<radialGradient id="spot" cx=".44" cy=".55" r=".55"><stop offset="0" stop-color="#3b4fd8" stop-opacity=".35"/><stop offset="1" stop-color="#3b4fd8" stop-opacity="0"/></radialGradient>
<linearGradient id="land" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1a2352"/><stop offset="1" stop-color="#0f1638"/></linearGradient>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="blur8"><feGaussianBlur stdDeviation="8"/></filter>
</defs>
<style>
.lane{{fill:none;stroke-width:1.6;stroke-linecap:round;opacity:.55}}
.bad{{stroke:#ef4444;stroke-dasharray:6 6;animation:dash 1s linear infinite, flick 2.4s ease-in-out infinite;opacity:.9}}
.rec{{stroke:#fbbf24;stroke-dasharray:3 7;animation:dash 1.4s linear infinite;opacity:.95}}
@keyframes dash{{to{{stroke-dashoffset:-24}}}}
@keyframes flick{{0%,100%{{opacity:.95}}50%{{opacity:.35}}}}
.ripple{{fill:none;stroke:#ef4444;stroke-width:2;transform-box:fill-box;transform-origin:center;animation:rip 2.4s ease-out infinite}}
.ripple.d2{{animation-delay:1.2s}}
@keyframes rip{{0%{{transform:scale(.3);opacity:1}}100%{{transform:scale(2.6);opacity:0}}}}
.stress{{animation:amber 2.4s ease-in-out infinite}}
@keyframes amber{{0%,100%{{opacity:.25}}50%{{opacity:.9}}}}
.rise{{transform-box:fill-box;transform-origin:50% 100%;animation:rise 1.2s cubic-bezier(.2,.9,.3,1.2) both}}
@keyframes rise{{from{{transform:scaleY(0);opacity:0}}to{{transform:scaleY(1);opacity:1}}}}
.lbl{{font:600 11px 'Segoe UI',Inter,Arial,sans-serif;fill:#cbd5f5}}
.sub{{font:500 10px 'Segoe UI',Inter,Arial,sans-serif;fill:#8590c0}}
.scan{{animation:scan 6s linear infinite}}
@keyframes scan{{0%{{transform:translateX(-200px)}}100%{{transform:translateX(1400px)}}}}
.blink{{animation:flick 1.6s ease-in-out infinite}}
</style>
<rect width="{W}" height="{H}" rx="20" fill="url(#bg)"/>
<rect width="{W}" height="{H}" rx="20" fill="url(#spot)"/>''')
    # iso grid
    for i in range(-22, 23, 2):
        a, b = iso(i, -22), iso(i, 22)
        c, d = iso(-22, i), iso(22, i)
        g.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="#6b7cff" stroke-opacity=".06"/>')
        g.append(f'<line x1="{c[0]:.1f}" y1="{c[1]:.1f}" x2="{d[0]:.1f}" y2="{d[1]:.1f}" stroke="#6b7cff" stroke-opacity=".06"/>')
    # India slab (extruded)
    poly = [plane(lo, la) for lo, la in INDIA]
    bottom = [iso(x, y, -14) for x, y in poly]
    topp = [iso(x, y) for x, y in poly]
    g.append(f'<polygon points="{pts(bottom)}" fill="#3b4fd8" opacity=".35" filter="url(#blur8)"/>')
    g.append(f'<polygon points="{pts(bottom)}" fill="#0a0f2a" stroke="#2a3a8a" stroke-width="1"/>')
    g.append(f'<polygon points="{pts(topp)}" fill="url(#land)" stroke="#5b6cff" stroke-opacity=".7" stroke-width="1.4"/>')
    g.append(f'<polygon points="{pts(topp)}" fill="none" stroke="#8ea0ff" stroke-width="3" opacity=".25" filter="url(#glow)"/>')

    built = {n["id"]: prism(n["id"]) for n in nodes}
    failed = "F1"
    downstream = {"S2", "W3", "F3"}
    stockout = "C3"
    # lanes
    lane_svg, particles = [], []
    for idx, e in enumerate(edges):
        s, t = e["source"], e["target"]
        (sx, sy), (tx, ty) = built[s][1], built[t][1]
        mx, my = (sx + tx) / 2, min(sy, ty) - 40 - math.hypot(tx - sx, ty - sy) * 0.18
        d = f"M{sx:.1f},{sy:.1f} Q{mx:.1f},{my:.1f} {tx:.1f},{ty:.1f}"
        src_col = COL[N[s]["kind"]][0]
        cls = "lane"
        stroke = src_col
        if s == failed:
            cls += " bad"
            stroke = "#ef4444"
        lane_svg.append(f'<path id="l{idx}" class="{cls}" d="{d}" stroke="{stroke}"/>')
        if s != failed:
            dur = 1.6 + float(e["lead"]) * 0.9
            pcol = "#e0e7ff"
            for k in range(2):
                particles.append(
                    f'<circle r="2.4" fill="{pcol}" filter="url(#glow)"><animateMotion dur="{dur:.1f}s" begin="{-k * dur / 2 - idx * .13:.2f}s" repeatCount="indefinite"><mpath href="#l{idx}"/></animateMotion></circle>')
    # nodes: ground shadows + stress halos first
    halos = []
    for nid, (_, _, (bx, by), _) in built.items():
        if nid == failed:
            halos.append(f'<ellipse class="ripple" cx="{bx:.1f}" cy="{by:.1f}" rx="26" ry="15"/>')
            halos.append(f'<ellipse class="ripple d2" cx="{bx:.1f}" cy="{by:.1f}" rx="26" ry="15"/>')
            halos.append(f'<ellipse cx="{bx:.1f}" cy="{by:.1f}" rx="30" ry="17" fill="#ef4444" opacity=".35" filter="url(#blur8)"/>')
        elif nid == stockout:
            halos.append(f'<ellipse class="ripple d2" cx="{bx:.1f}" cy="{by:.1f}" rx="20" ry="11" style="stroke:#f87171"/>')
            halos.append(f'<ellipse class="stress" cx="{bx:.1f}" cy="{by:.1f}" rx="20" ry="11" fill="#ef4444" opacity=".5"/>')
        elif nid in downstream:
            halos.append(f'<ellipse class="stress" cx="{bx:.1f}" cy="{by:.1f}" rx="22" ry="12" fill="none" stroke="#f59e0b" stroke-width="2"/>')
        else:
            halos.append(f'<ellipse cx="{bx:.1f}" cy="{by:.1f}" rx="18" ry="10" fill="none" stroke="#22c55e" stroke-width="1.2" opacity=".5"/>')
    g.append("\n".join(halos))
    g.append("\n".join(lane_svg))
    order = sorted(built.items(), key=lambda kv: kv[1][3])
    for i, (nid, (svg, (tx, ty), _, _)) in enumerate(order):
        extra = ' opacity=".55"' if nid == failed else ""
        g.append(f'<g{extra}>{svg}</g>')
    g.append("\n".join(particles))
    # labels for key sites
    offs = {"F1": (-95, -46), "C3": (-110, 34), "S2": (110, -52), "W3": (120, 18), "F3": (30, -105),
            "W2": (0, -34), "S4": (60, -40), "F2": (70, -50)}
    for nid, (dx, dy) in offs.items():
        (tx, ty) = built[nid][1]
        n = N[nid]
        col = "#fca5a5" if nid in (failed, stockout) else ("#fcd34d" if nid in downstream else "#cbd5f5")
        tag = {failed: " · DOWN", stockout: " · STOCK-OUT DAY 2"}.get(nid, " · STRESSED" if nid in downstream else "")
        anchor = "end" if dx < -10 else ("start" if dx > 10 else "middle")
        g.append(f'<polyline points="{tx:.1f},{ty:.1f} {tx + dx * .6:.1f},{ty + dy:.1f} {tx + dx:.1f},{ty + dy:.1f}" fill="none" stroke="{col}" stroke-opacity=".55"/>')
        g.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="2" fill="{col}"/>')
        g.append(f'<text class="lbl" x="{tx + dx + (4 if dx > 10 else -4 if dx < -10 else 0):.1f}" y="{ty + dy + (4 if anchor != "middle" else -6):.1f}" text-anchor="{anchor}" style="fill:{col}">{nid} {n["name"]}{tag}</text>')

    # HUD panel (right)
    hx = 930
    g.append(f'''<g font-family="'Segoe UI',Inter,Arial,sans-serif">
<rect x="{hx}" y="40" width="310" height="560" rx="16" fill="#0b1030" fill-opacity=".72" stroke="#3a4690" stroke-opacity=".6"/>
<circle class="blink" cx="{hx + 24}" cy="66" r="5" fill="#ef4444"/>
<text x="{hx + 38}" y="71" font-size="12" font-weight="700" fill="#fca5a5" letter-spacing="1.5">LIVE SCENARIO</text>
<text x="{hx + 22}" y="102" font-size="19" font-weight="700" fill="#f1f5ff">Factory F1 shuts · 10 days</text>
<text x="{hx + 22}" y="122" font-size="12" fill="#8f9bd0">Bengaluru Assembly · simulated by core/sim.py</text>
<line x1="{hx + 22}" y1="140" x2="{hx + 288}" y2="140" stroke="#2c3670"/>''')
    kpis = [("SURVIVAL CLOCK", "2 days", "#fbbf24", "C3 Bengaluru Retail runs out first"),
            ("UNMET DEMAND", "1,760 units", "#f87171", "revenue at risk ₹73.9 lakh"),
            ("HIDDEN PAIR (CHAOS FINDER)", "F1 + F2", "#f472b6", "together +3,100 units worse than alone"),
            ("RECOMMENDED: FULL PLAN", "₹47,500", "#34d399", "unmet down to 810 units, safety check passed")]
    y = 172
    for name, val, col, note in kpis:
        g.append(f'<text x="{hx + 22}" y="{y}" font-size="10.5" font-weight="700" fill="#7f8bc4" letter-spacing="1.2">{name}</text>')
        g.append(f'<text x="{hx + 22}" y="{y + 26}" font-size="22" font-weight="800" fill="{col}">{val}</text>')
        g.append(f'<text x="{hx + 22}" y="{y + 44}" font-size="11" fill="#8f9bd0">{note}</text>')
        y += 76
    # mini timeline bars (unmet per day)
    g.append(f'<text x="{hx + 22}" y="{y + 4}" font-size="10.5" font-weight="700" fill="#7f8bc4" letter-spacing="1.2">UNMET UNITS PER DAY · DAY 0-13</text>')
    vals = [0, 0, 220, 220, 220, 220, 220, 220, 220, 220, 0, 0, 0, 0]
    for i, v in enumerate(vals):
        bh = 4 + v / 220 * 46
        bx = hx + 22 + i * 19
        col = "#ef4444" if v > 0 else "#22c55e"
        g.append(f'<rect x="{bx}" y="{y + 66 - bh:.1f}" width="13" height="{bh:.1f}" rx="3" fill="{col}" opacity=".9">'
                 f'<animate attributeName="opacity" values=".25;1;.25" dur="2.8s" begin="{i * .2:.1f}s" repeatCount="indefinite"/></rect>')
    g.append('</g>')
    # legend + title
    lg = [("Supplier", "supplier"), ("Factory", "factory"), ("Warehouse", "warehouse"), ("Customer", "customer")]
    g.append(f'<text x="40" y="58" font-family="Segoe UI,Inter,Arial,sans-serif" font-size="13" font-weight="700" fill="#8ea0ff" letter-spacing="3">AEGIS · LIVE DIGITAL TWIN</text>')
    g.append(f'<text x="40" y="84" font-family="Segoe UI,Inter,Arial,sans-serif" font-size="22" font-weight="800" fill="#f1f5ff">16 sites · 23 lanes · 4 tiers across India</text>')
    lx = 40
    for name, kind in lg:
        g.append(f'<rect x="{lx}" y="{H - 52}" width="12" height="12" rx="3" fill="{COL[kind][1]}"/>')
        g.append(f'<text x="{lx + 18}" y="{H - 42}" class="lbl">{name}</text>')
        lx += 104
    for name, col, dash in [("Disrupted lane", "#ef4444", "5 4"), ("Stressed site", "#f59e0b", "2 2")]:
        g.append(f'<line x1="{lx}" y1="{H - 46}" x2="{lx + 22}" y2="{H - 46}" stroke="{col}" stroke-width="2" stroke-dasharray="{dash}"/>')
        g.append(f'<text x="{lx + 28}" y="{H - 42}" class="lbl">{name}</text>')
        lx += 140
    g.append(f'<rect class="scan" x="0" y="0" width="120" height="{H}" fill="#8ea0ff" opacity=".035"/>')
    g.append("</svg>")
    open(os.path.join(OUT, "hero-3d.svg"), "w", encoding="utf-8").write("\n".join(g))


def stats():
    items = [("318", "tests passing", "#34d399"), ("24,000", "simulated scenarios", "#a78bfa"),
             ("8", "insight detectors", "#60a5fa"), ("60", "candidate cities", "#2dd4bf"),
             ("100×", "Monte Carlo replays", "#fbbf24"), ("&lt; 1 s", "ML pre-screen of 2,000", "#f472b6")]
    w, h = 1280, 150
    g = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="318 tests, 24,000 simulated scenarios, 8 detectors, 60 candidate cities, 100 Monte Carlo replays, under 1 second ML pre-screen">
<style>
.card{{animation:up .8s cubic-bezier(.2,.9,.3,1) both}}
@keyframes up{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:none}}}}
.shine{{animation:sh 4s ease-in-out infinite}}
@keyframes sh{{0%{{transform:translateX(-80px)}}60%,100%{{transform:translateX(260px)}}}}
.num{{font:800 34px 'Segoe UI',Inter,Arial,sans-serif}}
.cap{{font:600 13px 'Segoe UI',Inter,Arial,sans-serif;fill:#9aa5d6}}
</style>
<defs><clipPath id="cc"><rect width="198" height="120" rx="14"/></clipPath>
<linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".09"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>''']
    for i, (num, cap, col) in enumerate(items):
        x = 8 + i * 212
        g.append(f'<g transform="translate({x},15)"><g class="card" style="animation-delay:{i * .12:.2f}s">'
                 f'<g clip-path="url(#cc)"><rect width="198" height="120" rx="14" fill="#0c1230"/>'
                 f'<rect width="198" height="4" fill="{col}"/>'
                 f'<rect class="shine" style="animation-delay:{i * .5:.1f}s" x="0" y="0" width="70" height="120" fill="url(#sg)"/></g>'
                 f'<rect width="198" height="120" rx="14" fill="none" stroke="{col}" stroke-opacity=".35"/>'
                 f'<text class="num" x="99" y="66" text-anchor="middle" fill="{col}">{num}</text>'
                 f'<text class="cap" x="99" y="94" text-anchor="middle">{cap}</text></g></g>')
    g.append("</svg>")
    open(os.path.join(OUT, "stats.svg"), "w", encoding="utf-8").write("\n".join(g))


def pipeline():
    steps = [("💥", "Disrupt", "plant fire, flood,\nfestival spike", "#ef4444"),
             ("📅", "Simulate", "day-by-day flow,\nSurvival Clock", "#60a5fa"),
             ("🎲", "Monte Carlo", "P50 / P90 loss,\nshortage odds", "#fbbf24"),
             ("🔍", "Chaos Finder", "every single &\nevery pair", "#f472b6"),
             ("🛟", "Recover", "cheapest SAFE\nplan wins", "#34d399"),
             ("🗺️", "Expand", "Dijkstra + MILP\nnew sites", "#2dd4bf")]
    w, h = 1280, 230
    n = len(steps)
    gap = (w - 120) / (n - 1)
    T = 9.0
    g = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="How AEGIS works: Disrupt, Simulate, Monte Carlo, Chaos Finder, Recover, Expand">
<defs><filter id="gl" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="6"/></filter>
<linearGradient id="track" x1="0" x2="1"><stop offset="0" stop-color="#ef4444"/><stop offset=".2" stop-color="#60a5fa"/><stop offset=".4" stop-color="#fbbf24"/><stop offset=".6" stop-color="#f472b6"/><stop offset=".8" stop-color="#34d399"/><stop offset="1" stop-color="#2dd4bf"/></linearGradient></defs>
<style>
.t{{font:700 17px 'Segoe UI',Inter,Arial,sans-serif;fill:#eef2ff}}
.d{{font:500 12px 'Segoe UI',Inter,Arial,sans-serif;fill:#8f9bd0}}
.e{{font:28px 'Segoe UI Emoji','Apple Color Emoji',sans-serif}}
.halo{{opacity:0;animation:on {T}s ease-in-out infinite}}
@keyframes on{{0%,100%{{opacity:0}}4%,14%{{opacity:.85}}22%{{opacity:0}}}}
.flow{{stroke-dasharray:10 14;animation:fl 1.2s linear infinite}}
@keyframes fl{{to{{stroke-dashoffset:-24}}}}
</style>
<rect width="{w}" height="{h}" rx="20" fill="#080c1f"/>
<line x1="60" y1="78" x2="{w - 60}" y2="78" stroke="#1f2850" stroke-width="6" stroke-linecap="round"/>
<line class="flow" x1="60" y1="78" x2="{w - 60}" y2="78" stroke="url(#track)" stroke-width="3" stroke-linecap="round"/>
<circle r="7" fill="#fff" filter="url(#gl)"><animate attributeName="cx" values="60;{w - 60}" dur="{T}s" repeatCount="indefinite"/><animate attributeName="cy" values="78;78" dur="{T}s" repeatCount="indefinite"/></circle>
<circle r="4" fill="#fff" cy="78"><animate attributeName="cx" values="60;{w - 60}" dur="{T}s" repeatCount="indefinite"/></circle>''']
    for i, (emo, title, desc, col) in enumerate(steps):
        x = 60 + i * gap
        delay = T * (i / (n - 1)) - 0.3
        g.append(f'<circle class="halo" style="animation-delay:{delay:.2f}s" cx="{x:.1f}" cy="78" r="40" fill="{col}" filter="url(#gl)"/>')
        g.append(f'<circle cx="{x:.1f}" cy="78" r="34" fill="#0e1433" stroke="{col}" stroke-width="2.5"/>')
        g.append(f'<text class="e" x="{x:.1f}" y="89" text-anchor="middle">{emo}</text>')
        g.append(f'<text class="t" x="{x:.1f}" y="146" text-anchor="middle">{title}</text>')
        for k, line in enumerate(desc.split("\n")):
            g.append(f'<text class="d" x="{x:.1f}" y="{168 + k * 16}" text-anchor="middle">{line.replace("&", "&amp;")}</text>')
        g.append(f'<text x="{x:.1f}" y="30" text-anchor="middle" font-family="Segoe UI,Arial" font-size="11" font-weight="700" fill="{col}" letter-spacing="2">STEP {i + 1}</text>')
    g.append("</svg>")
    open(os.path.join(OUT, "pipeline.svg"), "w", encoding="utf-8").write("\n".join(g))


hero(); stats(); pipeline()
print("ok")
