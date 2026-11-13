"""Generates locally stored SVG illustrations (no internet, no hotlinking). Replace any of them with a real photo by
dropping assets/images/<name>.jpg|webp|png - the app prefers a photo over the SVG if present.
Names: hero, f_inventory, f_forecast, f_supplier, f_recovery."""
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "images"
OUT.mkdir(parents=True, exist_ok=True)
BLUE, CYAN = "#1E6FD9", "#19B5D6"


def svg(w, h, body, title="", desc=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{title}">'
            f'<title>{title}</title><desc>{desc}</desc><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#0A2350"/><stop offset="1" stop-color="#0E3F86"/></linearGradient>'
            f'<linearGradient id="gl" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="{CYAN}" stop-opacity=".9"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#bg)"/>{body}</svg>')


def box(x, y, w, h, c):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{c}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h*0.22:.1f}" rx="2" fill="#fff" fill-opacity=".18"/>'
            f'<rect x="{x+w*0.3:.1f}" y="{y+h*0.5:.1f}" width="{w*0.4:.1f}" height="{h*0.12:.1f}" fill="#fff" fill-opacity=".55"/>')


def pill(x, y, r=1.0):
    return (f'<g transform="translate({x},{y}) rotate(-35) scale({r})"><rect x="-22" y="-9" width="44" height="18" rx="9" fill="#fff" fill-opacity=".95"/>'
            f'<rect x="-22" y="-9" width="22" height="18" rx="9" fill="{CYAN}"/></g>')


def hero():
    random.seed(4)
    b = ['<rect y="360" width="900" height="140" fill="#06183A"/>']
    for gx in range(0, 900, 30):
        b.append(f'<line x1="{gx}" y1="360" x2="{450 + (gx-450)*1.6:.0f}" y2="500" stroke="#1B4F9C" stroke-opacity=".3"/>')
    cols = ["#3C8DFF", "#19B5D6", "#7FB5FF", "#2A6FD0", "#58C8E8", "#9CC4FF"]
    for rack in range(5):
        x0 = 40 + rack * 170
        b.append(f'<rect x="{x0}" y="70" width="150" height="290" fill="#0B2F6B" stroke="#4FA3FF" stroke-opacity=".5"/>')
        for s in range(4):
            y = 90 + s * 68
            b.append(f'<rect x="{x0}" y="{y+52}" width="150" height="6" fill="#4FA3FF" fill-opacity=".8"/>')
            xx = x0 + 6
            while xx < x0 + 138:
                w = random.choice([22, 28, 34]); h = random.choice([30, 38, 46])
                if xx + w > x0 + 146:
                    break
                b.append(box(xx, y + 52 - h, w, h, random.choice(cols)))
                xx += w + 4
    b.append('<rect x="0" y="40" width="900" height="3" fill="url(#gl)"/>')
    for x, y in [(120, 395), (330, 420), (560, 400), (770, 430)]:
        b.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{CYAN}"/><circle cx="{x}" cy="{y}" r="16" fill="none" stroke="{CYAN}" stroke-opacity=".5"/>')
    b.append('<polyline points="120,395 330,420 560,400 770,430" fill="none" stroke="#19B5D6" stroke-width="2" stroke-dasharray="6 6"/>')
    b.append(pill(820, 90, 1.3) + pill(70, 30, 1.0))
    return svg(900, 500, "".join(b), "Illustration of a modern pharmaceutical warehouse with racked medicine cartons",
               "Locally generated vector illustration: warehouse racking, cartons and a distribution network.")


def f_inventory():
    b = [box(40 + i * 55, 200 - (40 + (i * 37) % 90), 44, 40 + (i * 37) % 90, [BLUE, CYAN, "#7FB5FF"][i % 3]) for i in range(6)]
    b.append('<rect x="30" y="200" width="340" height="5" fill="#fff" fill-opacity=".7"/>')
    b.append('<g transform="translate(300,60)"><rect width="80" height="60" rx="8" fill="#fff" fill-opacity=".92"/><rect x="10" y="14" width="60" height="6" fill="#0B2A5B"/><rect x="10" y="28" width="40" height="6" fill="#1E6FD9"/><rect x="10" y="42" width="50" height="6" fill="#19B5D6"/></g>')
    return svg(400, 240, "".join(b), "Medicine inventory shelves with stock level panel", "Vector illustration of stacked medicine cartons and a stock panel.")


def f_forecast():
    pts = [(30, 180), (80, 150), (130, 160), (180, 110), (230, 125), (280, 80), (330, 60)]
    line = " ".join(f"{x},{y}" for x, y in pts)
    b = [f'<polyline points="{line}" fill="none" stroke="#fff" stroke-opacity=".25" stroke-width="12"/>',
         f'<polyline points="{line}" fill="none" stroke="{CYAN}" stroke-width="4"/>']
    b += [f'<circle cx="{x}" cy="{y}" r="5" fill="#fff"/>' for x, y in pts]
    b.append('<path d="M230 125 L280 80 L330 60 L330 100 L280 120 Z" fill="#19B5D6" fill-opacity=".25"/>')
    b.append('<line x1="20" y1="205" x2="380" y2="205" stroke="#fff" stroke-opacity=".6"/>')
    return svg(400, 240, "".join(b), "Demand forecast line chart with confidence band", "Vector illustration of a rising demand forecast with an uncertainty band.")


def f_supplier():
    b = ['<rect x="40" y="120" width="120" height="60" rx="6" fill="#fff" fill-opacity=".92"/><rect x="160" y="140" width="60" height="40" rx="6" fill="#19B5D6"/>',
         '<circle cx="80" cy="190" r="14" fill="#06183A" stroke="#fff" stroke-width="4"/><circle cx="190" cy="190" r="14" fill="#06183A" stroke="#fff" stroke-width="4"/>',
         '<polyline points="250,170 300,120 350,150" fill="none" stroke="#fff" stroke-width="3" stroke-dasharray="6 6"/>']
    b += [f'<circle cx="{x}" cy="{y}" r="9" fill="{c}"/>' for x, y, c in [(250, 170, CYAN), (300, 120, "#F5A623"), (350, 150, "#7FB5FF")]]
    return svg(400, 240, "".join(b), "Delivery truck and logistics network nodes", "Vector illustration of a delivery truck and supply network.")


def f_recovery():
    b = ['<circle cx="120" cy="120" r="34" fill="#fff" fill-opacity=".92"/><circle cx="290" cy="80" r="26" fill="#19B5D6"/><circle cx="290" cy="170" r="26" fill="#7FB5FF"/>',
         '<path d="M154 112 L264 82" stroke="#fff" stroke-width="4"/><path d="M154 130 L264 166" stroke="#fff" stroke-width="4"/>',
         '<rect x="108" y="106" width="24" height="8" fill="#0B2A5B"/><rect x="116" y="98" width="8" height="24" fill="#0B2A5B"/>']
    return svg(400, 240, "".join(b), "Optimised stock transfers from a surplus site to shortage sites", "Vector illustration of redistribution arrows between facilities.")


for name, fn in [("hero", hero), ("f_inventory", f_inventory), ("f_forecast", f_forecast), ("f_supplier", f_supplier), ("f_recovery", f_recovery)]:
    (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print("wrote", name)
