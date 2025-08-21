import yaml
import os
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI


# 현재 파일 (explanation_generator.py) 위치 기준
BASE_DIR = Path(__file__).parent  # my_app/contents/recomendation
PROMPT_DIR = BASE_DIR / "prompts"  # my_app/contents/recomendation/prompts

def load_prompt(level: str):
    """
    YAML에서 레벨별 프롬프트 로드
    """
    file_path = PROMPT_DIR / f"{level.lower()}.yaml"
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_explanation(level: str, content_title: str, content_description: str) -> str:
    """
    Gemini를 사용하여 레벨별 맞춤 설명 생성
    """
    # Google API 키 불러오기
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("환경변수 GOOGLE_API_KEY가 설정되지 않았습니다.")

    # LLM 초기화
    llm_client = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.4,
        max_retries=2,
        google_api_key=api_key,
    )

    # 프롬프트 불러오기
    prompt_data = load_prompt(level)
    style = prompt_data["style"]
    example = prompt_data["example"]

    # 최종 사용자 프롬프트 구성
    user_prompt = f"""
    콘텐츠 제목: {content_title}
    콘텐츠 설명: {content_description}

    {style}

    참고 예시:
    {example}
    """

    # Gemini 호출
    response = llm_client.invoke(user_prompt)

    return response.content.strip()