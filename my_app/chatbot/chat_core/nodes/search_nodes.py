import json
import time
from datetime import datetime

from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate

from my_app.chatbot.chat_core.model_loader import (
    OPENAI_MODEL_NAME,
    get_llm_models,
)
from my_app.chatbot.chat_core.state import OverallState


def generate_queries_node(state: OverallState):
    llm = get_llm_models(OPENAI_MODEL_NAME)
    all_queries = []
    interests_categories = state.user_meta_data["interests_categories"]
    for category in interests_categories:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful research assistant. Your task is to generate 2-3 relevant and specific search queries for a given investment topic. Do not add numbers like '1.' or '2.' to the queries. Respond in the user's original language.",
                ),
                ("user", "Generate search queries for the following topic: {topic}"),
            ]
        )
        chain = prompt | llm
        response = chain.invoke({"topic": category})
        queries = [
            q.lstrip("0123456789. ") for q in response.content.split("\n") if q.strip()
        ]
        all_queries.extend(queries)

    return {
        "search_dataset": {
            **state.search_dataset,
            "search_queries": all_queries,
        },
        "messages": [],
        "logs": [
            {
                "level": "info",
                "message": f"검색어 생성 완료 (총 {len(all_queries)}개 검색어)",
                "timestamp": time.time(),
            }
        ],
    }


def web_search_node(state: OverallState):
    api_wrapper = DuckDuckGoSearchAPIWrapper(time="w")
    all_results = []
    for query in state.search_dataset["search_queries"]:
        parsed_results = api_wrapper.results(query, max_results=10)
        all_results.extend(parsed_results)

    cleaned_results = [
        {
            "title": res.get("title"),
            "url": res.get("link"),
            "snippet": res.get("snippet"),
        }
        for res in all_results
        if res.get("link") and res.get("title") and res.get("snippet")
    ]

    return {
        "messages": [],
        "logs": [
            {
                "level": "info",
                "message": f"웹 검색 완료 (총 {len(cleaned_results)}개 결과)",
                "timestamp": time.time(),
            }
        ],
        "search_dataset": {
            **state.search_dataset,
            "search_results": cleaned_results,
        },
    }


def batch_filter_node(state: OverallState):
    search_results = state.search_dataset["search_results"]
    if not search_results:
        return {"search_results": []}

    formatted_results = ""
    for i, res in enumerate(search_results):
        formatted_results += f"{i + 1}. Title: {res['title']}\n   Snippet: {res['snippet']}\n   Source URL: {res['url']}\n\n"

    batch_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a highly discerning financial analyst assistant. Your primary goal is to prioritize **objective, verifiable sources** over personal opinions. Review the numbered list of articles and select the ones most suitable for a data-driven investment report.

**Source Preference Hierarchy (Prioritize in this order):**
1.  **High-Quality Sources:** Reputable news outlets (e.g., Reuters, Bloomberg), official research reports (e.g., Gartner, Deloitte), government/institutional data, official company press releases.
2.  **Acceptable with Caution:** Well-known industry-specific publications or tech blogs from reputable companies (e.g., Google AI Blog), but only if they contain data and facts.
3.  **Generally Exclude:** Personal blogs (e.g., from Naver Blog, Tistory, Medium), marketing-focused company blogs, forums, or unverified sources.

**Inclusion Criteria (What to KEEP):**
- Articles from High-Quality Sources (Tier 1).
- Articles containing hard data, statistics, financial metrics (e.g., ROI, GDP, market size), even if from Tier 2 sources.

**Exclusion Criteria (What to DISCARD):**
- **Almost all articles from Tier 3 sources (personal blogs, marketing content).** Exclude them unless they present truly unique and verifiable data not found elsewhere.
- Basic definitions or encyclopedia entries.
- Articles focused on social/political controversies, opinions without data, or stereotypes.
- Promotional content, advertisements, or articles that primarily aim to sell a product.

Review the list below, paying close attention to the Source URL to judge the source's reliability. Respond with a JSON object containing a single key 'include_indices' with a list of the integer index numbers of the articles to keep.
Example: {{"include_indices": [1, 3, 8, 15]}}""",
            ),
            ("user", "Article List:\n\n{articles}"),
        ]
    )

    llm = get_llm_models(OPENAI_MODEL_NAME)

    filter_chain = batch_prompt | llm

    response = filter_chain.invoke({"articles": formatted_results})

    try:
        included_indices = json.loads(response.content).get("include_indices", [])
        final_results = [
            search_results[i - 1]
            for i in included_indices
            if 0 < i <= len(search_results)
        ]

        return {
            "search_dataset": {"search_results": final_results},
            "messages": [],
            "logs": [
                {
                    "level": "info",
                    "message": f"배치 필터링 완료 (통과: {len(final_results)}개 / 원본: {len(search_results)}개)",
                    "timestamp": time.time(),
                }
            ],
        }

    except (json.JSONDecodeError, AttributeError) as e:
        return {
            "search_dataset": {
                **state.search_dataset,
                "search_results": search_results,
            },
            "messages": [],
            "logs": [
                {
                    "level": "info",
                    "message": f"배치 필터링 오류: {e}. 필터링 없이 진행합니다.",
                    "timestamp": time.time(),
                }
            ],
        }


def generate_report_node(state: OverallState):
    today = datetime.now().strftime("%Y-%m-%d")
    categories_str = ", ".join(state.user_meta_data["interests_categories"])

    user_prompt = """
You are a veteran investment analyst with 15 years of experience. You specialize in analyzing {interests_categories}, and you are known for providing sober, data-driven analysis.

Synthesize news and market data for the 3-days period ending on `{today}` for {interests_categories} and draft an in-depth analysis report based on the format below.
You must go beyond simple news summarization and connect facts with data to provide persuasive insights.
**Crucially, you must use the real URLs provided in the search results to populate the 'links' section. Do not invent or use placeholder URLs.**

Always respond in Korean.

Please return nothing but a JSON in the following format

{{
    "summary": "A concise summary of the entire analysis in about 3 sentences.",
    "key_opportunities": [
        "A summary of the first key opportunity.",
        "A summary of the second key opportunity.",
        "A summary of the third key opportunity."
    ],
    "potential_risks": [
        "A summary of the first potential risk.",
        "A summary of the second potential risk.",
        "A summary of the third potential risk."
    ],
    "analyst_take": "Based on the analysis, provide your professional opinion on whether now is a suitable time to buy, hold, or sell. (Note: This is an opinion based on analysis, not direct investment advice.)",
    "links" : [
        {{
        "title": "Article Title or Brief Description 1",
        "url": "the source of data link 1"
        }},
        {{
        "title": "Article Title or Brief Description 2",
        "url": "the source of data link 2"
        }}
    ]
}}
"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", user_prompt),
            (
                "user",
                "Here are the pre-screened, objective search results from the last week:\n\n{search_results}",
            ),
        ]
    )

    llm = get_llm_models(OPENAI_MODEL_NAME)

    chain = prompt | llm

    search_results_str = "\n\n".join(
        [
            f"Title: {res['title']}\nURL: {res['url']}\nSnippet: {res['snippet']}"
            for res in state.search_dataset["search_results"]
        ]
    )

    response = chain.invoke(
        {
            "today": today,
            "interests_categories": categories_str,
            "search_results": search_results_str,
        }
    )

    result_json = json.loads(response.content)

    summary = result_json["summary"]
    key_opportunities = result_json["key_opportunities"]
    potential_risks = result_json["potential_risks"]
    analyst_take = result_json["analyst_take"]
    links = result_json["links"]

    summary_message = AIMessage(
        content=f"관심 분야에 대한 최신 뉴스를 정리해봤어요. \n\n {summary}"
    )
    key_opportunities_message = []
    for i in range(len(key_opportunities)):
        key_opportunities_message.append(f"{i + 1}. {key_opportunities[i]}")

    key_opportunities_message = AIMessage(
        content="현재 해당 분야의 최적의 투자 기회는 다음과 같습니다. \n"
        + "\n".join(key_opportunities_message)
    )
    potential_risks_message = []
    for i in range(len(potential_risks)):
        potential_risks_message.append(f"{i + 1}. {potential_risks[i]}")

    potential_risks_message = AIMessage(
        content="현재 해당 분야의 주의해야 할 리스크는 다음과 같습니다. \n"
        + "\n".join(potential_risks_message)
    )
    analyst_take_message = AIMessage(
        content=f"저의 최종 의견은 다음과 같습니다. \n\n {analyst_take}"
    )

    links_message = []
    for i in range(len(links)):
        links_message.append(f"{i + 1}. {links[i]['title']} \n {links[i]['url']}")

    links_message = AIMessage(
        content="제가 찾아본 데이터의 참고 자료 링크입니다. \n "
        + "\n".join(links_message)
    )

    return {
        "search_dataset": {
            **state.search_dataset,
            "report": result_json,
        },
        "messages": [
            summary_message,
            key_opportunities_message,
            potential_risks_message,
            analyst_take_message,
            links_message,
        ],
        "logs": [
            {
                "level": "info",
                "message": "보고서 생성 완료",
                "timestamp": time.time(),
            }
        ],
    }
