# 룰+벡터 후보 → 가중치 리랭킹 recommend()
from typing import List, Dict, Tuple, Set
from data_access import load_all_cards
from context_builder import build_user_context_text
from vector_search import vector_candidates

# ---- 룰 후보 (레벨/태그 기반) ----
def rule_candidates(cards: List[Dict], user_level: str, interest_tags: List[str], k: int = 10,
                    exclude_ids: Set[str] = None) -> List[str]:
    exclude_ids = exclude_ids or set()
    itags = set([t.strip() for t in (interest_tags or []) if t.strip()])
    scored: List[Tuple[float, str]] = []

    for c in cards:
        if c["card_id"] in exclude_ids:
            continue
        level_bonus = 1.0 if str(c.get("level")) == str(user_level) else 0.0
        overlap = len(itags.intersection(set(c.get("tags") or [])))
        tag_bonus = 1.0 if overlap > 0 else 0.0  # 간단화
        score = 0.7 * level_bonus + 0.3 * tag_bonus
        if score > 0:
            scored.append((score, c["card_id"]))

    scored.sort(reverse=True)
    return [cid for _, cid in scored[:k]]

# ---- 리랭킹 ----
def rerank(candidates: List[str], user: Dict, cards: List[Dict], faiss_scores: Dict[str, float],
           alpha: float = 0.7, beta: float = 0.2, gamma: float = 0.1, top_n: int = 3) -> List[str]:
    itags = set(user.get("interest_tags") or [])
    seen = set(user.get("recent_seen_card_ids") or [])
    liked_tags = set(user.get("liked_tags") or [])

    card_map = {c["card_id"]: c for c in cards}
    scored: List[Tuple[float, str]] = []

    for cid in candidates:
        c = card_map.get(cid)
        if not c:
            continue
        vec = float(faiss_scores.get(cid, 0.0))
        lvl = 1.0 if str(c.get("level")) == str(user.get("level")) else 0.0
        overlap = len(itags.intersection(set(c.get("tags") or [])))
        tag_ratio = overlap / max(1, len(itags))

        score = alpha * vec + beta * lvl + gamma * tag_ratio

        if cid in seen:
            score -= 0.2
        if liked_tags.intersection(set(c.get("tags") or [])):
            score += 0.1

        scored.append((score, cid))

    scored.sort(reverse=True)
    return [cid for _, cid in scored[:top_n]]

# ---- 엔드투엔드 ----
def recommend(user: Dict, top_n: int = 3, k_vec: int = 10, k_rule: int = 10,
              alpha: float = 0.7, beta: float = 0.2, gamma: float = 0.1) -> Dict:
    """
    user 예시 (로그 없어도 OK):
      {
        "user_id": "u001",
        "level": "Beginner",
        "interest_tags": ["ETF","저위험","반도체"],
        "style": "쉬운 언어와 비유 중심",
        "recent_seen_card_ids": [],
        "liked_tags": []
      }
    """
    cards = load_all_cards()

    # 1) 사용자 컨텍스트 → 텍스트
    ctx_text = build_user_context_text(user, logs=None)  # 콜드 스타트도 처리함

    # 2) 벡터 후보
    try:
        vec_ids, vec_scores = vector_candidates(ctx_text, k=k_vec)
        faiss_scores = {cid: s for cid, s in zip(vec_ids, vec_scores)}
    except Exception as e:
        # 인덱스가 아직 없다면(최초 실행 등) 벡터 없이 진행
        vec_ids, faiss_scores = [], {}
        print(f"[WARN] 벡터 검색 실패: {e} → 룰베이스만 사용")

    # 3) 룰 후보
    rule_ids = rule_candidates(cards, user.get("level"), user.get("interest_tags"), k=k_rule,
                               exclude_ids=set(user.get("recent_seen_card_ids") or []))

    # 4) 후보 합치기 (중복 제거 후 최대 10개)
    merged = []
    seen = set()
    for cid in rule_ids + vec_ids:
        if cid not in seen:
            merged.append(cid)
            seen.add(cid)
        if len(merged) >= 10:
            break

    # 5) 리랭킹
    final_ids = rerank(merged, user, cards, faiss_scores, alpha=alpha, beta=beta, gamma=gamma, top_n=top_n)

    # 6) 결과 구성(메타 포함 반환)
    card_map = {c["card_id"]: c for c in cards}
    results = [card_map[cid] for cid in final_ids if cid in card_map]

    return {
        "context_text": ctx_text,
        "candidates_rule": rule_ids,
        "candidates_vec": vec_ids,
        "results": results
    }