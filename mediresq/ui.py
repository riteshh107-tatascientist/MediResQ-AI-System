"""Shared UI helpers: theme CSS (with left-to-right light sweep), hero header, local image embedding, chart styling."""
import base64
from pathlib import Path

from . import config

NAVY, BLUE, CYAN = "#0B2A5B", "#1E6FD9", "#19B5D6"
AMBER, RED, GREEN, GREY = "#F5A623", "#D64545", "#2E9E6B", "#8A97AD"
SEV_COLOR = {"Critical": RED, "High": "#E8742B", "Medium": AMBER, "Low": GREEN}

CSS = """
<style>
:root{--navy:#0B2A5B;--blue:#1E6FD9;--cyan:#19B5D6;--ink:#10223F;--muted:#5B6B86;--line:#E3E9F3;--card:#FFFFFF;}
html,body,[class*="css"]{font-family:"Inter","Segoe UI",system-ui,-apple-system,Roboto,sans-serif;}
.stApp{background:#F6F9FE;}
.block-container{padding-top:1.2rem;max-width:1400px;}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#071A3A 0%,#0B2A5B 100%);}
section[data-testid="stSidebar"] *{color:#E8F0FF !important;}
section[data-testid="stSidebar"] .stRadio label{padding:4px 2px;}
.hero{position:relative;overflow:hidden;border-radius:18px;padding:34px 38px;margin-bottom:18px;color:#fff;
 background:linear-gradient(135deg,#061633 0%,#0A2656 55%,#0D3B7A 100%);border:1px solid rgba(90,175,255,.38);
 box-shadow:0 0 0 1px rgba(0,200,255,.10),0 14px 40px rgba(7,26,58,.32),inset 0 0 70px rgba(0,160,255,.10);}
.hero.compact{padding:20px 28px}
.hero::before{content:"";position:absolute;top:0;bottom:0;left:-35%;width:28%;pointer-events:none;z-index:1;
 background:linear-gradient(100deg,transparent 0%,rgba(25,181,214,0) 25%,rgba(130,225,255,.30) 50%,rgba(25,181,214,0) 75%,transparent 100%);
 transform:skewX(-18deg);animation:mrq-sweep 6s linear infinite;}
.hero::after{content:"";position:absolute;top:0;bottom:0;left:-35%;width:2px;pointer-events:none;z-index:1;
 background:linear-gradient(180deg,transparent,rgba(160,235,255,.95),transparent);box-shadow:0 0 14px 3px rgba(60,200,255,.55);
 transform:skewX(-18deg);animation:mrq-sweep2 6s linear infinite;}
@keyframes mrq-sweep{0%{left:-35%}100%{left:112%}}
@keyframes mrq-sweep2{0%{left:-21%}100%{left:126%}}
@media (prefers-reduced-motion: reduce){.hero::before,.hero::after{animation:none !important;opacity:0}}
.hero .in{position:relative;z-index:2;display:grid;grid-template-columns:1.15fr 1fr;gap:28px;align-items:center}
.hero.compact .in{grid-template-columns:1fr}
.eyebrow{font-size:.78rem;letter-spacing:.16em;text-transform:uppercase;color:#8FD8FF;font-weight:600}
.hero h1{font-size:3.6rem;line-height:1.02;margin:.25rem 0 .35rem;font-weight:800;letter-spacing:-.02em;color:#fff}
.hero.compact h1{font-size:2.3rem}
.tag{font-size:1.25rem;font-weight:600;color:#D6EBFF;margin:0 0 .4rem}
.sub{font-size:1rem;color:#B7CCEA;margin:0 0 .9rem;max-width:560px}
.chip{display:inline-block;font-size:.74rem;letter-spacing:.12em;font-weight:600;color:#BFE9FF;border:1px solid rgba(143,216,255,.45);
 padding:5px 12px;border-radius:999px;background:rgba(13,59,122,.5)}
.hero img{width:100%;border-radius:14px;border:1px solid rgba(143,216,255,.35);box-shadow:0 10px 30px rgba(0,0,0,.35);display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:0 2px 10px rgba(11,42,91,.06);height:100%}
.card h4{margin:.2rem 0 .3rem;color:var(--navy);font-size:1.02rem}
.card p{color:var(--muted);font-size:.9rem;margin:0}
.fcard img{width:100%;border-radius:10px;margin-bottom:8px;display:block}
.kpi{background:#fff;border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:12px;padding:12px 14px;box-shadow:0 2px 8px rgba(11,42,91,.06)}
.kpi .v{font-size:1.65rem;font-weight:700;color:var(--navy);line-height:1.1}
.kpi .l{font-size:.74rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.kpi.red{border-left-color:#D64545}.kpi.amber{border-left-color:#F5A623}.kpi.green{border-left-color:#2E9E6B}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;justify-content:space-between}
.step{flex:1;min-width:150px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center;position:relative}
.step b{display:block;color:var(--navy)}.step span{font-size:.82rem;color:var(--muted)}
.step .n{width:26px;height:26px;border-radius:50%;background:var(--blue);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:.8rem;margin-bottom:6px}
.arrow{align-self:center;color:var(--cyan);font-size:1.4rem}
.sim{display:inline-block;background:#FFF4DB;color:#8A5A00;border:1px solid #F5D58A;border-radius:6px;padding:2px 8px;font-size:.75rem;font-weight:600}
.note{background:#EAF3FF;border:1px solid #CFE2FF;border-radius:10px;padding:10px 14px;color:#143A73;font-size:.88rem}
.sevpill{padding:2px 8px;border-radius:999px;color:#fff;font-size:.74rem;font-weight:600}
@media (max-width:900px){.hero .in{grid-template-columns:1fr}.hero h1{font-size:2.6rem}.arrow{display:none}}
</style>
"""


def inject_css(st):
    st.markdown(CSS, unsafe_allow_html=True)


def img_data_uri(name):
    d = config.ASSET_DIR / "images"
    for ext, mime in ((".webp", "image/webp"), (".jpg", "image/jpeg"), (".jpeg", "image/jpeg"), (".png", "image/png"), (".svg", "image/svg+xml")):
        p = d / f"{name}{ext}"
        if p.exists():
            return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    return ""


def img_tag(name, alt):
    uri = img_data_uri(name)
    return f'<img src="{uri}" alt="{alt}" loading="lazy"/>' if uri else ""


def hero_home():
    return (f'<div class="hero"><div class="in"><div>'
            f'<div class="eyebrow">SAP HACKFEST 2026 | WEST &amp; CENTRAL REGION</div>'
            f'<h1>MediResQ AI</h1><p class="tag">Predict. Protect. Prevent Shortages.</p>'
            f'<p class="sub">AI-Powered Essential Medicine Supply Chain Resilience.</p>'
            f'<span class="chip">TIT BHOPAL | CSE (DATA SCIENCE)</span></div>'
            f'<div>{img_tag("hero", "Illustration of a modern pharmaceutical warehouse with racked medicine cartons and a distribution network")}</div>'
            f'</div></div>')


def hero_app(title="MediResQ AI", subtitle="Predict. Protect. Resilience in Every Medicine Supply Chain.",
             desc="Intelligent forecasting, disruption detection and optimized medicine recovery."):
    return (f'<div class="hero compact"><div class="in"><div>'
            f'<div class="eyebrow">SAP HACKFEST 2026 | WEST &amp; CENTRAL</div>'
            f'<h1>{title}</h1><p class="tag">{subtitle}</p><p class="sub">{desc}</p>'
            f'<span class="chip">TIT BHOPAL | CSE (DATA SCIENCE)</span></div></div></div>')


def kpi(label, value, tone=""):
    return f'<div class="kpi {tone}"><div class="l">{label}</div><div class="v">{value}</div></div>'


def style(fig, height=340):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(family="Inter, Segoe UI, sans-serif", color="#10223F", size=12),
                      colorway=[BLUE, CYAN, AMBER, RED, GREEN, GREY], legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(gridcolor="#EEF2F9")
    fig.update_yaxes(gridcolor="#EEF2F9")
    return fig


def sim_badge():
    return '<span class="sim">SIMULATED / SYNTHETIC DATA</span>'
