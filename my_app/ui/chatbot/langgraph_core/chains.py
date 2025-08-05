# langgraph_core/chains.py

from jinja2 import Template  # Jinja2 라이브러리 import
from langchain_core.runnables import RunnableLambda

from .llm_agents import GEMINI_MODEL_NAME, get_llm_agents
from .prompt_loader import load_prompt

onboarding_template_string = load_prompt("system_prompts")
template = Template(onboarding_template_string)


def _render_onboarding_prompt(input_dict: dict):
    user_data = input_dict.get("user_data")
    rendered_prompt_string = template.render(user_data=user_data)
    return rendered_prompt_string


# prompt_renderer = RunnableLambda(_render_onboarding_prompt)

# onboarding_chain = (
#     prompt_renderer | get_llm_agents(GEMINI_MODEL_NAME)  # 팩토리에서 LLM 가져오기
# )


# 방법 1: RunnableLambda로 직접 처리
def _process_onboarding(input_dict: dict):
    user_data = input_dict.get("user_data", {})
    user_message = input_dict.get("user_message", [])
    
    # 사용자 메시지에서 실제 content 추출
    if user_message and hasattr(user_message[-1], 'content'):
        latest_message = user_message[-1].content
    else:
        latest_message = "안녕하세요"

    # 프롬프트 렌더링 - Jinja2 템플릿에 필요한 변수들 전달
    rendered_prompt = template.render(
        user_data=user_data, 
        latest_message=latest_message
    )
    
    # 렌더링된 프롬프트가 비어있지 않은지 확인
    if not rendered_prompt.strip():
        rendered_prompt = "안녕하세요! 저는 자산구조원 AI입니다. 투자에 대해 궁금한 것이 있으시면 언제든 물어보시겠어요?"

    # LLM 호출
    llm = get_llm_agents(GEMINI_MODEL_NAME)
    response = llm.invoke(rendered_prompt)

    return response


onboarding_chain = RunnableLambda(_process_onboarding)
