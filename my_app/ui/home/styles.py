import streamlit as st

def inject_home_styles():
    st.markdown("""
    <style>
      :root {
        --ink:#0f172a; --muted:#475569; --border:rgba(148,163,184,.28);
        --chip:#f8fafc; --chip-text:#0f172a; --accent:#4f46e5; --green:#10b981;
      }
      .home-hero{background:linear-gradient(135deg,rgba(79,70,229,.12),rgba(16,185,129,.12));
        border-radius:20px;padding:40px 30px;text-align:center;margin-bottom:24px}
      .home-hero h1{font-size:2.2rem;font-weight:900;color:var(--ink);margin:0 0 .5rem}
      .home-hero p{font-size:1.05rem;color:var(--muted);margin:0}

      /* profile */
      .profile-pro{width:100%}
      .profile-cover{padding:18px 20px;border-bottom:1px solid var(--border);
        background:radial-gradient(800px 300px at 0% 0%,rgba(79,70,229,.16),transparent 60%),
                   radial-gradient(800px 300px at 100% 0%,rgba(16,185,129,.16),transparent 60%),
                   linear-gradient(135deg,#eef2ff,#f0fdf4)}
      .p-head{display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:center}
      @media (max-width:420px){.p-head{grid-template-columns:auto 1fr}.p-actions{grid-column:1/-1;justify-content:flex-end;margin-top:8px}}
      .ava{width:72px;height:72px;border-radius:18px;display:grid;place-items:center;font-weight:900;font-size:1.15rem;color:#0f172a;background:#fff;border:1px solid var(--border);box-shadow:0 6px 16px rgba(2,6,23,.06)}
      .p-name{font-weight:900;font-size:1.15rem;color:var(--ink)}
      .p-email{font-size:.9rem;color:var(--muted);margin-top:2px}
      .p-pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
      .pill{display:inline-flex;gap:6px;align-items:center;padding:6px 10px;border-radius:999px;background:#fff;border:1px solid var(--border);font-size:.86rem}
      .p-body{padding:16px 18px}
      .p-grid{display:grid;gap:12px;grid-template-columns:1fr}
      @media (min-width:1280px){.p-grid{grid-template-columns:220px 1fr 1fr}}
      .card{border:1px solid var(--border);border-radius:14px;background:#fff;padding:14px}
      .card label{display:block;font-size:.84rem;color:var(--muted);margin-bottom:6px}
      .chips{display:flex;flex-wrap:wrap;gap:8px}
      .chip{background:var(--chip);color:var(--chip-text);border:1px solid var(--border);border-radius:999px;padding:4px 10px;font-size:.85rem}
      .mini-grid{display:grid;gap:12px;grid-template-columns:1fr 1fr;margin-top:12px}
      @media (max-width:1300px){.mini-grid{grid-template-columns:1fr}}
      .ring{--p:0;width:90px;height:90px;border-radius:50%;background:conic-gradient(var(--accent) calc(var(--p)*1%),#e2e8f0 0);position:relative}
      .ring::before{content:"";position:absolute;inset:10px;border-radius:50%;background:#fff}
      .ring .v{position:absolute;inset:0;display:grid;place-items:center;font-weight:900;font-size:.95rem;color:var(--ink)}
      .sum{border:1px solid var(--border);border-radius:14px;background:#fff;padding:14px;font-size:.94rem}
      .sum h4{margin:0 0 8px 0;font-size:.95rem}

      /* feature cards */
      .feature-card{border:1px solid var(--border);border-radius:16px;padding:24px;background:#fff;transition:all .2s ease;height:100%}
      .feature-card:hover{box-shadow:0 6px 18px rgba(0,0,0,.10);transform:translateY(-3px)}
      .feature-title{font-weight:700;margin-top:10px;font-size:1.1rem}
      .feature-desc{font-size:.95rem;opacity:.9;margin-top:6px}
      .card-link,.card-link:link,.card-link:visited,.card-link:hover,.card-link:active{text-decoration:none!important;color:inherit!important;display:block!important}
      .card-link .feature-card{cursor:pointer}
      .arrow-col{text-align:center;font-size:2rem;line-height:150px;opacity:.6;user-select:none}
      .down-arrow{text-align:center;font-size:2rem;margin:10px 0;opacity:.6;user-select:none}

      /* portfolio/news */
      .kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}
      @media (max-width:1100px){.kpi-row{grid-template-columns:1fr 1fr}}
      .kpi{border:1px solid var(--border);border-radius:14px;background:#fff;padding:14px}
      .kpi small{color:var(--muted);display:block;margin-bottom:6px}
      .kpi b{font-size:1.2rem;color:var(--ink)}
      .kpi .pos{color:#059669}.kpi .neg{color:#dc2626}
      .port-card{border:1px solid var(--border);border-radius:16px;background:#fff;color:var(--ink);padding:16px}
      .port-title{font-weight:800;margin-bottom:10px;display:flex;align-items:center;gap:8px}
      .badge-soft{font-size:.8rem;padding:2px 8px;border-radius:999px;border:1px solid var(--border);color:var(--muted)}
      .table-hint{color:var(--muted);font-size:.9rem;margin-top:6px}
      .empty{border:1px dashed var(--border);border-radius:14px;padding:16px;background:#fff;color:var(--muted)}
      .subcard{border:1px solid var(--border);border-radius:16px;background:#fff;padding:14px}
      .subcard h4{margin:0 0 8px 0;font-size:1rem}
      .news-list{display:grid;grid-template-columns:1fr;gap:10px}
      .news-item{border:1px solid var(--border);border-radius:12px;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;background:#fff}
      .news-item .meta{color:var(--muted);font-size:.86rem}
      .news-item a{text-decoration:none}
      .tag{font-size:.78rem;padding:2px 8px;border-radius:999px;border:1px solid var(--border);color:var(--muted)}

      /* floating toast */
      .floating-wrap{position:fixed;right:22px;bottom:22px;z-index:9999;width:360px;max-width:calc(100vw - 40px)}
      .ft-hide{position:absolute;opacity:0;pointer-events:none}
      .floating-toast{background:#fff;border:1px solid var(--border);border-radius:14px;box-shadow:0 12px 28px rgba(2,6,23,.15);padding:14px 16px;transition:opacity .25s,transform .25s;animation:ft-slide-in .25s ease, ft-disappear var(--auto,12s) linear forwards}
      @keyframes ft-slide-in{from{transform:translateY(12px);opacity:0}to{transform:translateY(0);opacity:1}}
      @keyframes ft-disappear{0%{opacity:1;transform:translateY(0)}92%{opacity:1;transform:translateY(0)}100%{opacity:0;transform:translateY(8px)}}
      .ft-hide:checked + .floating-toast{opacity:0;transform:translateY(8px);pointer-events:none}
      .floating-toast .ft-title{font-weight:800;margin:0 24px 6px 0;color:var(--ink)}
      .floating-toast .ft-msg{color:var(--muted);font-size:.92rem}
      .floating-toast .ft-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
      .ft-btn{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:10px;border:1px solid var(--border);background:#fff;color:var(--ink);text-decoration:none}
      .ft-btn.primary{background:#111827;border-color:#111827;color:#fff}
      .floating-toast .ft-close{position:absolute;top:8px;right:8px;cursor:pointer;font-size:18px;line-height:1;color:#94a3b8}
      .floating-toast .ft-close:hover{color:#0f172a}
    </style>
    """, unsafe_allow_html=True)
