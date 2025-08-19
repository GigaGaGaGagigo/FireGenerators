import os
import re
import json
import google.generativeai as genai
from dotenv import load_dotenv

# ── ENV ───────────────────────────────────────────────────────────────────────
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")

SAVE_PATH = "my_app/qa_chat_bot/data/quiz_questions.json"

# ── Utils ─────────────────────────────────────────────────────────────────────
def extract_json_array(text: str) -> str:
    """코드펜스/부가텍스트 제거 후 JSON 배열만 추출."""
    t = text.strip()
    t = re.sub(r"^```json\s*|\s*```$", "", t, flags=re.IGNORECASE)
    m = re.search(r"\[[\s\S]*\]", t)
    if not m:
        raise ValueError("JSON 배열을 찾지 못했습니다. 원문:\n" + text[:500])
    return m.group(0)

def normalize_questions(items: list) -> list:
    """
    생성 결과를 안전한 스키마로 보정.
    - 필수 필드 채움
    - OX vs 객관식 규칙 확인
    - level→weight 매핑 보정
    - 정확히 10문항으로 맞춤(부족분 패딩)
    """
    out = []
    for it in items:
        q = {
            "question_text": str(it.get("question_text", "")).strip(),
            "answer": str(it.get("answer", "")).strip(),
            "explanation": str(it.get("explanation", "")).strip(),
            "level": (it.get("level") or "easy").strip().lower(),
        }
        q["weight"] = 2 if q["level"] == "medium" else 1

        options = it.get("options", [])
        if isinstance(options, list):
            options = [str(x).strip() for x in options][:4]
        else:
            options = []

        # 필수 검증
        if not q["question_text"] or not q["answer"] or not q["explanation"]:
            continue

        a = q["answer"].upper()
        if a in {"O", "X"}:
            q["answer"] = a
            q["options"] = []
        else:
            if a not in {"1", "2", "3", "4"}:
                continue
            if len(options) != 4:
                continue
            q["options"] = options

        out.append(q)
        if len(out) == 10:
            break

    # 부족분 패딩(OX 쉬운 문항)
    while len(out) < 10:
        out.append({
            "question_text": "분산투자는 특정 종목 위험을 줄이는 데 도움이 된다. (O/X)",
            "answer": "O",
            "explanation": "여러 자산에 나눠 투자하면 개별 리스크가 완화된다.",
            "level": "easy",
            "weight": 1,
            "options": []
        })

    return out

# ── Prompts ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
너는 한국어 금융 교육 전문가야. 사용자의 관심사를 반영해 초·중급 난이도의 퀴즈 10문항을 만든다.

요구사항:
- 정확히 10문제.
- 각 문항 형식:
  1) O/X (정답: "O" 또는 "X")
  2) 4지선다 (정답: "1"~"4")
- 각 문항 필드(JSON):
  - question_text (string, 한국어)
  - answer (string: "O"/"X" 또는 "1"~"4")
  - explanation (string, 핵심 근거)
  - level (string: "easy" 또는 "medium")
  - weight (int: easy=1, medium=2)
  - options (array of 4 strings)  # 객관식일 때만. O/X는 생략 또는 빈 배열.
- 출력은 오직 JSON 배열만. 마크다운/부가텍스트 금지.
"""

USER_PROMPT_TMPL = """
사용자 관심사 키워드: {keywords_str}

예시 스키마(참고용):
[
  {{
    "question_text": "예금자보호제도는 1인당 1기관 기준으로 5천만원까지 보호한다. (O/X)",
    "answer": "O",
    "explanation": "예금보험공사는 1인당 1기관 기준 5천만원 한도로 보호한다.",
    "level": "easy",
    "weight": 1
  }},
  {{
    "question_text": "ETF의 특징으로 옳지 않은 것은?",
    "answer": "3",
    "explanation": "모든 ETF가 원금 보장되는 것은 아니다.",
    "level": "medium",
    "weight": 2,
    "options": ["1. 실시간 매매", "2. 분산투자", "3. 원금 보장", "4. 낮은 보수 가능"]
  }}
]

위 요구를 만족하는 실제 10문항 JSON 배열만 출력해줘.
"""

# ── Generator ─────────────────────────────────────────────────────────────────
def generate_quiz_by_keywords(user_keywords: list) -> list:
    """키워드 기반 10문항 생성 → 정규화된 list 반환."""
    keywords_str = ", ".join([str(k) for k in (user_keywords or [])]) or "주식, 채권, 예금, ETF, 세제혜택, ISA"
    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content([SYSTEM_PROMPT, USER_PROMPT_TMPL.format(keywords_str=keywords_str)])
    raw = (resp.text or "").strip()
    json_str = extract_json_array(raw)
    items = json.loads(json_str)
    questions = normalize_questions(items)
    return questions

def save_questions_local(questions: list, path: str = SAVE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print(f"[OK] saved: {path}")

if __name__ == "__main__":
    # 데모: 키워드 없이 생성
    qs = generate_quiz_by_keywords([])
    save_questions_local(qs)