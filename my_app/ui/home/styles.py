import streamlit as st
from .utils import html, asset_b64

def inject_home_styles():
    st.markdown("""
    <style>
       /* ====== FULL HERO ====== */
      :root{
        --ink:#0f172a; --muted:#475569; --border:rgba(148,163,184,.28);
        --accent:#16a34a; /* green-600 */
        --accent2:#2563eb; /* blue-600 */
      } 
      html{ scroll-behavior:smooth; }

      .mega-hero{
        min-height: 88vh;  /* 화면 꽉 채우기 */
        width: 100%;
        border-radius: 24px;
        padding: clamp(28px, 4vw, 48px);
        display:grid;
        grid-template-columns: 1.2fr 1fr;
        gap: clamp(20px, 3vw, 40px);
        align-items: center;
        position: relative;
        background:
          radial-gradient(900px 380px at 0% 0%, rgba(37,99,235,.12), transparent 60%),
          radial-gradient(900px 380px at 100% 0%, rgba(22,163,74,.14), transparent 60%),
          linear-gradient(135deg, #f0f9ff, #ecfdf5);
        border:1px solid var(--border);
      }
      @media (max-width: 980px){
        .mega-hero{ grid-template-columns: 1fr; min-height: 78vh; }
      }

      .hero-title{ font-weight:900; line-height:1.1; color:var(--ink);
                   font-size: clamp(34px, 4.6vw, 54px); margin:0 0 10px; }
      .hero-sub{
        font-size: clamp(16px, 1.6vw, 20px);  /* 살짝 업 */
        line-height: 1.6;                     /* 가독성 보정 */
        color: var(--muted);
        margin: 0 0 18px;
      }
      .hero-logo{
        position: absolute;
        right: clamp(16px, 3vw, 44px);
        top: clamp(18px, 6vh, 68px);
        width: clamp(120px, 13vw, 220px);     /* 크기 반응형 */
        pointer-events: none;                 /* 클릭 막기 */
        user-select: none;
        opacity: .96;
        filter: drop-shadow(0 18px 36px rgba(2,6,23,.25));
        z-index: 4;                           /* 카드 위로 */
      }
      @media (max-width: 900px){
        .hero-logo{ right: 12px; top: 12px; width: 120px; }
      }                
      .hero-bullets{ display:grid; gap:10px; margin:18px 0 26px; }
      .hero-bullets .item{
        display:flex; gap:10px; align-items:flex-start;
        background:#fff; border:1px solid var(--border); border-radius:14px;
        padding:10px 12px;
      }
      .dot{ width:18px; height:18px; border-radius:50%;
            background:linear-gradient(135deg,var(--accent),var(--accent2)); }

      .cta-row{ display:flex; gap:12px; flex-wrap:wrap; }
      .cta{
        display:inline-flex; align-items:center; gap:8px;
        background:linear-gradient(135deg,var(--accent),var(--accent2));
        color:#fff; padding:12px 18px; border-radius:12px; text-decoration:none;
        font-weight:700; border:0;
        box-shadow:0 10px 24px rgba(37,99,235,.18);
      }
      .cta:hover{ transform: translateY(-1px); }
      .ghost{
        display:inline-flex; align-items:center; gap:8px;
        padding:11px 16px; border-radius:12px; text-decoration:none;
        background:#fff; color:var(--ink); border:1px solid var(--border);
      }

      /* phone mock */
      .phone{
        width: min(380px, 90%); margin-inline: auto;
        border-radius: 28px; padding: 18px;
        background: #0a0f1f;
        color: #e5e7eb;
        border: 1px solid rgba(255,255,255,.08);
        box-shadow: 0 30px 60px rgba(2,6,23,.20);
      }
      .ph-top{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
      .ph-bal{ font-weight:800; font-size:22px; }
      .ph-chip{ font-size:12px; padding:4px 8px; border-radius:999px; border:1px solid rgba(255,255,255,.12); }
      .ph-list{ display:grid; gap:8px; margin-top:10px; }
      .ph-row{
        display:grid; grid-template-columns: 1fr auto; gap:8px;
        padding:10px 12px; border-radius:12px; background:rgba(255,255,255,.04);
        border:1px solid rgba(255,255,255,.06);
      }
      .ph-sym{ font-weight:700; }
      .ph-pl.pos{ color:#34d399; } .ph-pl.neg{ color:#f87171; }

      /* 섹션 앵커(히어로 밑으로 스크롤) */
      .anchor{ scroll-margin-top: 24px; }

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
                
      /* ==== News-only Cards ==== */
      .news-grid{
        display:grid;
        grid-template-columns: 1fr 1fr;
        gap:10px;
        text-decoration: none;   /* 밑줄 제거 */        
      }
      @media (max-width: 1100px){
        .sq-row{ grid-template-columns: 1fr; }
        .sq-inner .ring{ --size: clamp(120px, 38vw, 180px); --thick: 20px; }
        .emotion-card .radar-img{ max-width: clamp(200px, 60vw, 420px); }
      }

      .news-card{
        display:block;
        text-decoration:none;
        border:1px solid var(--border);
        border-radius:14px;
        background:#fff;
        padding:12px 14px;
        transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
        color:var(--ink);
      }
      .news-card:hover{
        transform: translateY(-2px);
        box-shadow:0 10px 22px rgba(2,6,23,.10);
        border-color: rgba(37,99,235,.35);
        color: var(--accent2);   /* 호버 시 색만 변하도록 */
        text-decoration: none;   /* 호버 때도 밑줄 X */
      }
      .news-tag{
        display:inline-flex; align-items:center; gap:6px;
        font-size:.78rem;
        padding:3px 8px;
        border-radius:999px;
        background:#eef2ff;
        color:#1e3a8a;
        border:1px solid rgba(37,99,235,.18);
        margin-bottom:6px;
      }
      .news-meta{
        font-size:.86rem; color:var(--muted);  color:var(--muted);
      }
                
      .news-grid a,
      .news-card,
      .news-card:link,
      .news-card:visited,
      .news-card:hover,
      .news-card:active {
        text-decoration: none !important;
        border-bottom: none !important; /* 일부 테마가 밑줄 대신 border-bottom 사용 */
        outline: none;
        color: var(--ink);
      }

      .news-card * {
        text-decoration: none !important; /* 앵커 내부 모든 자식에도 강제 */
        border-bottom: none !important;
      }

      .news-title {
        font-weight:800; line-height:1.35; margin:2px 0 4px 0; font-size:.98rem;
        color: var(--ink); text-decoration: none !important;
      }
      .news-card:hover .news-title { color: var(--accent2); }
    
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
      /* === 정사각형 카드 행(리스크/감정) === */
      .sq-row{
        grid-column: 1 / -1;                   
        display: grid;
        grid-template-columns: repeat(2, 1fr);  /* 큼직하게 */
        gap: 16px;
      }
      @media (max-width: 1200px){
        .sq-row{ grid-template-columns: 1fr; }  /* 좁을 땐 세로 스택 */
      }

      /* 카드 자체 */
      .card.sq{
        display:flex; align-items:center; justify-content:center;
        padding: 100px;
      }
                
      /* 정사각형 카드 전체(이미 사용 중이면 그대로) */
      .square-card{
        border:1px solid var(--border);
        border-radius:16px;
        background:#fff;
        padding:18px;
        min-height: 300px;          /* 너무 낮지 않게만 */
        display:flex; align-items:center; justify-content:center;
      }

      /* 감정 카드: 왼쪽에 그래프, 오른쪽 좁은 타이틀 레일 */
      .emotion-card{
        display:flex; align-items:center; justify-content:space-between; width:100%;
      }
                
      /* --- 카드 상단 제목 공통 --- */
      .card-head{
        width:100%;
        font-weight:800;
        /* 글씨 크기 업 */
        font-size: clamp(1.0rem, 1.3vw, 1.35rem);
        color: var(--ink);
        margin-bottom: 10px;
      }

      /* 리스크 카드: 제목은 위, 도넛과 설명은 아래 가로배치 */
      .square-card.risk-card{
        display:flex; flex-direction:column; align-items:flex-start;
      }
      .square-card.risk-card .sq-inner{
        width:100%;
        display:flex; align-items:center; gap:16px;
      }
      .square-card.risk-card .ring{
        /* 크기 살짝 줄여 반반 느낌 유지 */
        --size: clamp(140px, 20vw, 190px);
        --thick: 24px;
        width: var(--size); height: var(--size);
        border-radius:50%;
        background: conic-gradient(var(--accent) calc(var(--p)*1%), #e2e8f0 0);
        position: relative;
      }
      .square-card.risk-card .ring::before{ content:""; position:absolute; inset: var(--thick); border-radius:50%; background:#fff; }
      .square-card.risk-card .ring .v{ position:absolute; inset:0; display:grid; place-items:center; font-weight:900; }

      /* 감정분석 카드: 제목을 위 가로, 그래프는 크게 중앙 */
      .square-card.emotion-card{
        display:grid;
        grid-template-rows: auto 1fr;
        grid-template-columns: 1fr;
        align-items:center;
      }
      .square-card.emotion-card .card-head{
        grid-row:1; grid-column:1; justify-self:start;
      }
      .square-card.emotion-card .radar-img{
        grid-row:2; grid-column:1; justify-self:center;
        /* 그래프 조금 더 키움 */
        max-width: clamp(280px, 40vw, 560px);
        height:auto;
      }
      .emotion-card .radar-img{
        flex:1 1 auto;
        max-width: clamp(220px, 34vw, 460px);   /* 화면에 맞게 반응형 */
        height:auto;
      }
      /* 세로 레일(감정분석 글자) */
      .sq-rail-title{ display:none !important; }


      /* 카드 안 레이아웃 */
      .sq-inner{
        display:flex; align-items:center; gap:16px;
      }
      .sq-inner.col{ flex-direction:column; }

      /* 큼직한 제목 */
      .sq-title{ font-weight:800; margin:0 0 8px; font-size:1.05rem; }

      /* 큰 도넛 */
      .ring{
        --p:0; --size:260px; --thick:28px;
        width: var(--size);
        height: var(--size);
        border-radius:50%;
        background: conic-gradient(var(--accent) calc(var(--p)*1%), #e2e8f0 0);
        position: relative;
      }
      .sq-inner .ring{
        /* 화면에 따라: 최소 140px ~ 최대 200px */
        --size: clamp(140px, 22vw, 200px);
        --thick: 24px;
        width: var(--size);
        height: var(--size);
        border-radius:50%;
        background: conic-gradient(var(--accent) calc(var(--p)*1%), #e2e8f0 0);
        position: relative;
        flex: 0 0 auto;          /* 텍스트 영역과 반반 느낌 */
      }
      .ring::before{ content:""; position:absolute; inset: var(--thick); border-radius:50%; background:#fff; }
      .ring .v{ position:absolute; inset:0; display:grid; place-items:center; font-weight:900; }

      /* 레이더 이미지가 카드 안에서 깔끔히 보이게 */
      .radar-img{
        width: 88%;
        height: 78%;
        max-width: 520px;
        object-fit: contain;
        display:block;
        margin: 4px auto 0;
      }
                
      
                

      

    </style>
    """, unsafe_allow_html=True)

def render_full_hero(usdkrw: float | None = None):
    rate_txt = f"{usdkrw:,.2f}" if usdkrw else "—"


    html(
        """
        <section class="mega-hero">
          <div>
            <h1 class="hero-title">FIREGENERATOR로<br/>더 똑똑하게 투자하세요</h1>
            <p class="hero-sub">
              챗봇에서 목표·감정·관심사·투자 수준을 입력하고 상담을 시작하세요.
              오늘의 퀴즈로 현재 지식을 점검한 뒤, 결과와 관심사에 맞춘 금융 콘텐츠를 학습하고<br/>
              관심 종목 피드백과 보유주식 AI 코칭으로 전략을 다듬은 다음,
              투자 성향에 맞는 맞춤형 상품 추천까지 받아보세요.
            </p>

          </div>

          <div>
            <div class="phone">
              <div class="ph-top">
                <div class="ph-bal">₩ 25,901,000</div>
                <div class="ph-chip">USDKRW """ + rate_txt + """</div>
              </div>
              <div class="ph-list">
                <div class="ph-row"><div class="ph-sym">AAPL</div><div class="ph-pl pos">+5.2%</div></div>
                <div class="ph-row"><div class="ph-sym">TSLA</div><div class="ph-pl neg">-1.8%</div></div>
                <div class="ph-row"><div class="ph-sym">MSFT</div><div class="ph-pl pos">+0.9%</div></div>
                <div class="ph-row"><div class="ph-sym">NVDA</div><div class="ph-pl pos">+2.4%</div></div>
              </div>
            </div>
          </div>
        </section>
        """
    )
