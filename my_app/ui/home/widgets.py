from .utils import html

def render_link_card(title: str, desc: str, icon: str, page_key: str):
    html(f"""
    <a class="card-link hash-nav" href="#nav={page_key}">
      <div class="feature-card">
        <div style="font-size:2rem;">{icon}</div>
        <div class="feature-title">{title}</div>
        <div class="feature-desc">{desc}</div>
      </div>
    </a>
    """)
