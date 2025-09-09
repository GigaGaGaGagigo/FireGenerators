import yaml
import os
import sys
from pathlib import Path
from typing import Optional

# 경로 설정
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent  # my_app
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_google_genai import ChatGoogleGenerativeAI
from contents.recommendation.user_contents_logger import get_logger


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


def generate_explanation(level: str, content_title: str, content_description: str, contents_id: Optional[str] = None) -> str:
    """
    Gemini를 사용하여 레벨별 맞춤 설명 생성.
    DB에 캐시된 설명이 있으면 먼저 반환.
    """
    logger = get_logger()
    # 1. DB에서 캐시된 설명 확인
    if contents_id and logger:
        cached_explanation = logger.get_cached_explanation(contents_id=contents_id, user_level=level)
        if cached_explanation:
            return cached_explanation

    # 2. 캐시 없으면 LLM 호출
    # GEMINI API 키 불러오기
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("환경변수 GEMINI_API_KEY가 설정되지 않았습니다.")

    # Google Application Credentials 환경변수 제거 (충돌 방지)
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        del os.environ['GOOGLE_APPLICATION_CREDENTIALS']

    # LLM 초기화
    llm_client = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
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

    # response.content가 문자열인지 확인 후 안전하게 처리
    content = response.content
    if isinstance(content, str):
        explanation = content.strip()
    else:
        # content가 리스트나 다른 타입인 경우 문자열로 변환
        explanation = str(content).strip()

    return explanation