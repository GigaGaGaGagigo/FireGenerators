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
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from contents.recommendation.user_contents_logger import get_logger


# 현재 파일 (explanation_generator.py) 위치 기준
BASE_DIR = Path(__file__).parent  # my_app/contents/recommendation
PROMPT_DIR = BASE_DIR / "prompts"  # my_app/contents/recommendation/prompts


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
    Gemini → OpenAI → Claude 순으로 LLM 호출.
    DB에 캐시된 설명이 있으면 먼저 반환.
    """
    logger = get_logger()
    if contents_id and logger:
        cached_explanation = logger.get_cached_explanation(contents_id=contents_id, user_level=level)
        if cached_explanation:
            return cached_explanation

    # 프롬프트 불러오기
    prompt_data = load_prompt(level)
    style = prompt_data["style"]
    example = prompt_data["example"]

    user_prompt = f"""
    콘텐츠 제목: {content_title}
    콘텐츠 설명: {content_description}

    {style}

    참고 예시:
    {example}
    """

    # LLM 순차 실행
    llm_client = None
    response = None
    errors = []

    # 1️⃣ Gemini 시도
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
                del os.environ['GOOGLE_APPLICATION_CREDENTIALS']
            llm_client = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0.4,
                max_retries=2,
                google_api_key=gemini_key,
            )
            response = llm_client.invoke(user_prompt)
        except Exception as e:
            errors.append(f"Gemini 실패: {e}")

    # 2️⃣ OpenAI 시도
    if response is None:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                llm_client = ChatOpenAI(
                    model="gpt-4o-mini",  # 가볍고 저렴한 모델
                    temperature=0.4,
                    api_key=openai_key,
                )
                response = llm_client.invoke(user_prompt)
            except Exception as e:
                errors.append(f"OpenAI 실패: {e}")

    # 3️⃣ Claude 시도
    if response is None:
        claude_key = os.getenv("CLAUDE_API_KEY")
        if claude_key:
            try:
                llm_client = ChatAnthropic(
                    model="claude-3-5-sonnet-20240620",
                    temperature=0.4,
                    max_tokens=512,
                    api_key=claude_key,
                )
                response = llm_client.invoke(user_prompt)
            except Exception as e:
                errors.append(f"Claude 실패: {e}")

    if response is None:
        raise RuntimeError(f"모든 LLM 호출 실패: {errors}")

    # 응답 처리
    content = getattr(response, "content", None) or str(response)
    return content.strip()