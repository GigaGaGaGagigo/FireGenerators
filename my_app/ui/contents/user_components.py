# ================== 
# 사용자 뷰 UI 컴포넌트들
# ================== 
import streamlit as st
import datetime
from typing import Dict, List, Any

from ui.contents.data_utils import (
    get_emotion_status, get_risk_tolerance_status,
    safe_tags, calculate_completion_rate, format_datetime_string,
    process_feedback_for_reranking, adjust_scores_by_feedback,
    load_and_analyze_contents, get_feedback_display_info
)
from ui.contents.styles import (
    get_profile_card_style, get_quiz_card_style, get_ai_explanation_style,
    get_content_card_style, get_tag_style, get_celebration_style, apply_quiz_styles
)
from ui.contents.constants import DEFAULT_CONFIG

# 추천 시스템 모듈들을 함수 내에서 import하도록 변경
def get_recommendation_modules():
    """추천 시스템 모듈들을 동적으로 import"""
    contents_rec_path = None
    try:
        # 경로 설정
        import sys
        import os
        from pathlib import Path
        import importlib.util
        
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        contents_rec_path = os.path.join(str(project_root), "contents", "recommendation")
        
        # sys.path에 필요한 경로들 추가 (hybrid_recommender_v2.py의 의존성 해결)
        if contents_rec_path not in sys.path:
            sys.path.insert(0, contents_rec_path)
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # 필요한 파일들 경로
        hybrid_file = os.path.join(contents_rec_path, "hybrid_recommender_v2.py")
        explanation_file = os.path.join(contents_rec_path, "explanation_generator.py")
        logger_file = os.path.join(contents_rec_path, "user_contents_logger.py")
        data_access_file = os.path.join(contents_rec_path, "data_access.py")
        context_builder_file = os.path.join(contents_rec_path, "context_builder.py")
        vector_search_file = os.path.join(contents_rec_path, "vector_search.py")
        
        # 파일 존재 확인
        missing_files = []
        required_files = {
            "hybrid_recommender_v2.py": hybrid_file,
            "explanation_generator.py": explanation_file,
            "user_contents_logger.py": logger_file,
            "data_access.py": data_access_file,
            "context_builder.py": context_builder_file,
            "vector_search.py": vector_search_file
        }
        
        for filename, filepath in required_files.items():
            if not os.path.exists(filepath):
                missing_files.append(filename)
        
        if missing_files:
            st.error(f"필요한 파일을 찾을 수 없습니다: {', '.join(missing_files)}")
            st.info(f"검색 경로: {contents_rec_path}")
            return None, None, None
        
        # 모든 모듈 스펙을 먼저 생성
        hybrid_spec = importlib.util.spec_from_file_location("hybrid_recommender_v2", hybrid_file)
        if hybrid_spec is None or hybrid_spec.loader is None:
            raise ImportError("hybrid_recommender_v2 모듈을 찾을 수 없습니다")
        hybrid_module = importlib.util.module_from_spec(hybrid_spec)
        
        explanation_spec = importlib.util.spec_from_file_location("explanation_generator", explanation_file)
        if explanation_spec is None or explanation_spec.loader is None:
            raise ImportError("explanation_generator 모듈을 찾을 수 없습니다")
        explanation_module = importlib.util.module_from_spec(explanation_spec)
        
        logger_spec = importlib.util.spec_from_file_location("user_contents_logger", logger_file)
        if logger_spec is None or logger_spec.loader is None:
            raise ImportError("user_contents_logger 모듈을 찾을 수 없습니다")
        logger_module = importlib.util.module_from_spec(logger_spec)
        
        data_access_spec = importlib.util.spec_from_file_location("data_access", data_access_file)
        if data_access_spec is None or data_access_spec.loader is None:
            raise ImportError("data_access 모듈을 찾을 수 없습니다")
        data_access_module = importlib.util.module_from_spec(data_access_spec)
        
        context_builder_spec = importlib.util.spec_from_file_location("context_builder", context_builder_file)
        if context_builder_spec is None or context_builder_spec.loader is None:
            raise ImportError("context_builder 모듈을 찾을 수 없습니다")
        context_builder_module = importlib.util.module_from_spec(context_builder_spec)
        
        vector_search_spec = importlib.util.spec_from_file_location("vector_search", vector_search_file)
        if vector_search_spec is None or vector_search_spec.loader is None:
            raise ImportError("vector_search 모듈을 찾을 수 없습니다")
        vector_search_module = importlib.util.module_from_spec(vector_search_spec)
        
        # 모든 모듈을 sys.modules에 미리 등록 (서로 참조 가능하게 함)
        sys.modules["hybrid_recommender_v2"] = hybrid_module
        sys.modules["explanation_generator"] = explanation_module
        sys.modules["user_contents_logger"] = logger_module
        sys.modules["data_access"] = data_access_module
        sys.modules["context_builder"] = context_builder_module
        sys.modules["vector_search"] = vector_search_module
        
        # contents.recommendation 패키지도 가상으로 생성
        import types
        contents_package = types.ModuleType('contents')
        recommendation_package = types.ModuleType('contents.recommendation')
        setattr(recommendation_package, 'user_contents_logger', logger_module)
        setattr(contents_package, 'recommendation', recommendation_package)
        sys.modules['contents'] = contents_package
        sys.modules['contents.recommendation'] = recommendation_package
        sys.modules['contents.recommendation.user_contents_logger'] = logger_module
        
        # 의존성 순서대로 모든 모듈을 실행
        data_access_spec.loader.exec_module(data_access_module)  # 다른 모듈에서 많이 참조됨
        context_builder_spec.loader.exec_module(context_builder_module)
        vector_search_spec.loader.exec_module(vector_search_module)
        logger_spec.loader.exec_module(logger_module)
        explanation_spec.loader.exec_module(explanation_module)  # logger를 참조
        hybrid_spec.loader.exec_module(hybrid_module)  # 모든 모듈을 참조
        
        # 함수 존재 확인
        if not hasattr(hybrid_module, 'get_hybrid_recommendations'):
            st.error("get_hybrid_recommendations 함수를 찾을 수 없습니다.")
            return None, None, None
        if not hasattr(explanation_module, 'generate_explanation'):
            st.error("generate_explanation 함수를 찾을 수 없습니다.")
            return None, None, None
        if not hasattr(logger_module, 'get_logger'):
            st.error("get_logger 함수를 찾을 수 없습니다.")
            return None, None, None
        
        return hybrid_module.get_hybrid_recommendations, explanation_module.generate_explanation, logger_module.get_logger
        
    except Exception as e:
        st.error(f"추천 시스템 모듈을 불러올 수 없습니다: {e}")
        st.error(f"오류 상세: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        st.info(f"경로 확인: {contents_rec_path if 'contents_rec_path' in locals() else '경로 설정 실패'}")
        return None, None, None


def render_user_profile_card(profile_data: Dict[str, Any]) -> None:
    """사용자 프로필 카드 렌더링"""
    user_name = profile_data['user_name']
    user_level = profile_data['user_level']
    knowledge_level = profile_data['knowledge_level']
    emotions = profile_data['emotions']
    interest_tags = profile_data['interest_tags']
    risk_tolerance = profile_data['risk_tolerance']
    
    emotion_info = get_emotion_status(emotions)
    risk_info = get_risk_tolerance_status(risk_tolerance)
    
    main_profile_text = f"""
    <p>👋 안녕하세요, <strong>{user_name}</strong>님! 챗봇과 퀴즈로 분석한 당신의 금융 프로필을 알려드릴게요.</p>
    <p>*상세한 프로필 내용은 홈 화면에서 확인 가능합니다.</p>
    <br>
    <p>🏦 <strong>금융 지식 수준:</strong> {user_level} ({knowledge_level})</p>
    <p>💭 <strong>현재 투자 심리:</strong> {emotion_info['emoji']} {emotion_info['status']}</p>
    <p>📊 <strong>투자 성향:</strong> {risk_info['emoji']} {risk_info['status']}</p>
    <p>💡 <strong>관심 분야:</strong> {', '.join(interest_tags) if interest_tags else '아직 설정되지 않음'}</p>
    <br>
    <p>이제 금융 프로필을 바탕으로 <strong>{user_name}</strong>님의 지식 레벨을 높일 시간입니다. 맞춤 추천 받기 버튼을 누르면 당신을 위한 맞춤 정보가 추천됩니다.🙌</p>
    """
    
    st.markdown(get_profile_card_style(main_profile_text), unsafe_allow_html=True)


def render_user_analysis_cards(profile_data: Dict[str, Any]) -> None:
    """사용자 분석 결과 카드들 렌더링"""
    user_name = profile_data['user_name']
    user_summary = profile_data['user_summary']
    knowledge_summary = profile_data['knowledge_summary']
    
    # 퀴즈 스타일 적용
    apply_quiz_styles()
    
    # 투자 성향 분석
    if user_summary and user_summary.strip() and user_summary not in ['NULL', 'null', 'None']:
        content = user_summary
    else:
        content = f"💬 {user_name}님, 챗봇과 대화를 나누시면 투자 성향을 분석해드릴게요!"
    
    st.markdown(get_quiz_card_style(f"📑 {user_name}님의 투자 성향", content), unsafe_allow_html=True)
    
    # 금융 지식 수준 분석
    if knowledge_summary and knowledge_summary.strip() and knowledge_summary not in ['NULL', 'null', 'None']:
        content = knowledge_summary
    else:
        content = f"📝 {user_name}님, 퀴즈를 완료하시면 금융 지식 수준을 분석해드릴게요!"
    
    st.markdown(get_quiz_card_style(f"🎓 {user_name}님의 금융 레벨", content), unsafe_allow_html=True)


def render_recommendation_button(
    interest_tags: List[str], 
    profile_data: Dict[str, Any], 
    top_n: int, 
    use_llm_rerank: bool
) -> None:
    """맞춤 추천 버튼 렌더링 및 처리"""
    if 'recommendation_result' not in st.session_state:
        if st.button("💫 맞춤 추천 받기", use_container_width=True):
            if not interest_tags:
                st.warning("관심 분야를 최소 1개 선택해주세요!")
                st.stop()
            
            # 추천 모듈 동적 import
            get_hybrid_recommendations, _, _ = get_recommendation_modules()
            if not get_hybrid_recommendations:
                return
            
            spinner_text = "🐾 AI가 맞춤 정보를 찾고 있어요..." if use_llm_rerank else "🚥 맞춤 정보를 찾고 있어요..."
            with st.spinner(spinner_text):
                rec_result = get_hybrid_recommendations({
                    "user_id": f"user_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "level": profile_data['knowledge_level'],
                    "emotions": profile_data['emotions'],
                    "interest_tags": interest_tags,
                    "recent_seen_card_ids": [],
                    "liked_tags": [],
                    "user_summary": profile_data['user_summary'],
                    "knowledge_summary": profile_data['knowledge_summary']
                }, top_n=top_n, use_llm_rerank=use_llm_rerank)
            
            if rec_result["success"]:
                st.session_state['recommendation_result'] = rec_result
                st.session_state['shown_recommendations'] = rec_result['results']
                st.rerun()
            else:
                st.error("추천을 가져올 수 없어요. 잠시 후 다시 시도해주세요.")


def render_content_explanation_section(content: Dict, profile_data: Dict, i: int) -> None:
    """콘텐츠 설명 생성 섹션 렌더링"""
    card_identifier = content.get('card_id', content.get('id', i))
    explanation_key = f"explanation_{card_identifier}"
    log_id_key = f"log_id_{card_identifier}"

    col_btn, col_exp = st.columns([1, 2])
    
    with col_btn:
        if st.button("💡 AI 맞춤 설명", key=f"user_explain_btn_{card_identifier}"):
            with st.spinner("당신을 위한 맞춤 설명을 만들고 있어요..."):
                try:
                    # 모듈 동적 import
                    _, generate_explanation, get_logger = get_recommendation_modules()
                    if not generate_explanation or not get_logger:
                        st.error("설명 생성 모듈을 불러올 수 없습니다.")
                        return
                    
                    explanation = generate_explanation(
                        level=profile_data['knowledge_level'],
                        content_title=content.get('title',''),
                        content_description=content.get('content','')[:300],
                        contents_id=content.get('id')
                    )
                    st.session_state[explanation_key] = explanation
                    
                    # 실시간 로그 저장
                    try:
                        supabase_client = st.session_state.get("supabase")
                        logger = get_logger(supabase_client)
                        if logger:
                            user_data = st.session_state.get('user_data', {})
                            user_id = user_data.get('id', 'anonymous')
                            contents_id_for_log = content.get('id')

                            if contents_id_for_log:
                                user_context = {
                                    'emotions': profile_data['emotions'],
                                    'interest_tags': profile_data['interest_tags'],
                                    'risk_tolerance': profile_data.get('risk_tolerance', 50),
                                    'investment_goal': profile_data.get('investment_goal', ''),
                                    'user_summary': profile_data.get('user_summary', ''),
                                    'knowledge_summary': profile_data.get('knowledge_summary', '')
                                }
                                
                                log_id = logger.log_content_view(
                                    user_id=str(user_id),
                                    contents_id=contents_id_for_log,
                                    content_title=content.get('title', ''),
                                    original_content=content.get('content', ''),
                                    ai_explanation=explanation,
                                    user_level=profile_data['knowledge_level'],
                                    user_context=user_context,
                                    recommendation_source=content.get('recommendation_source', 'unknown'),
                                    recommendation_rank=content.get('recommendation_rank', i)
                                )
                                if log_id:
                                    st.session_state[log_id_key] = log_id
                            else:
                                st.warning(f"콘텐츠의 UUID가 없어 로그 저장이 불가능합니다: card_id={content.get('card_id')}")

                    except Exception as log_error:
                        st.error(f"로그 저장 중 오류 발생: {log_error}")
                    
                    st.success("✅ 설명이 준비됐어요!")
                except Exception as e:
                    st.error(f"설명을 만들 수 없어요 😅: {e}")
    
    with col_exp:
        if explanation_key in st.session_state:
            st.markdown(
                get_ai_explanation_style(st.session_state[explanation_key]),
                unsafe_allow_html=True
            )
            
            # 피드백 버튼 렌더링
            render_feedback_buttons(card_identifier, log_id_key)


def render_feedback_buttons(card_identifier: str, log_id_key: str) -> None:
    """피드백 버튼 렌더링"""
    feedback_recorded_key = f"feedback_recorded_{card_identifier}"
    
    if log_id_key in st.session_state and feedback_recorded_key not in st.session_state:
        st.write("이 설명이 도움이 되었나요?")
        fb_cols = st.columns([1, 1, 8])
        
        with fb_cols[0]:
            if st.button("👍", key=f"fb_pos_{card_identifier}"):
                _, _, get_logger = get_recommendation_modules()
                if get_logger:
                    supabase_client = st.session_state.get("supabase")
                    logger = get_logger(supabase_client)
                    if logger:
                        logger.log_feedback(st.session_state[log_id_key], 'positive')
                        st.toast("피드백 감사합니다! 👍")
                        st.session_state[feedback_recorded_key] = 'positive'
                        st.rerun()
        
        with fb_cols[1]:
            if st.button("👎", key=f"fb_neg_{card_identifier}"):
                _, _, get_logger = get_recommendation_modules()
                if get_logger:
                    supabase_client = st.session_state.get("supabase")
                    logger = get_logger(supabase_client)
                    if logger:
                        logger.log_feedback(st.session_state[log_id_key], 'negative')
                        st.toast("피드백 감사합니다! 개선에 참고할게요.")
                        st.session_state[feedback_recorded_key] = 'negative'
                        st.rerun()
    
    elif feedback_recorded_key in st.session_state:
        if st.session_state[feedback_recorded_key] == 'positive':
            st.success("👍 피드백이 반영되었습니다.")
        else:
            st.warning("👎 아쉬운 점을 알려주셔서 감사합니다.")


def render_recommendation_contents(results: List[Dict], profile_data: Dict) -> None:
    """추천 콘텐츠 목록 렌더링"""
    st.success("✨ 맞춤 정보가 추천되었습니다!")
    st.markdown('### 🚀 나만의 맞춤 추천')

    for i, content in enumerate(results, 1):
        st.markdown(
            get_content_card_style(f"{i}. {content.get('title','제목 없음')}"),
            unsafe_allow_html=True
        )

        # 설명 생성 섹션
        render_content_explanation_section(content, profile_data, i)

        # 태그 표시
        tags = safe_tags(content.get('tags', []))
        if tags:
            tag_html = get_tag_style(tags, DEFAULT_CONFIG["max_display_tags"])
            st.markdown(tag_html, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)


def render_more_recommendations_button(rec_result: Dict, results: List[Dict]) -> None:
    """추가 추천 버튼 렌더링"""
    all_candidates = rec_result['metadata']['all_candidates']
    shown_ids = {c['card_id'] for c in st.session_state['shown_recommendations']}
    more_available = len(all_candidates) > len(shown_ids)

    if more_available:
        if st.button("🔄 새로운 맞춤 정보 더 보기", use_container_width=True):
            with st.spinner("피드백을 반영하여 새로운 정보를 찾고 있어요..."):
                handle_more_recommendations(rec_result, results, all_candidates, shown_ids)
    else:
        st.info("모든 추천 후보를 확인했습니다. 😃")


def handle_more_recommendations(rec_result: Dict, results: List[Dict], all_candidates: List, shown_ids: set) -> None:
    """추가 추천 처리 로직"""
    base_scores = rec_result['metadata']['base_scores']
    previous_results = st.session_state['shown_recommendations']
    
    # 피드백 수집
    feedback = process_feedback_for_reranking(previous_results, dict(st.session_state))
    
    # 콘텐츠 데이터 로드
    analysis = load_and_analyze_contents()
    if not analysis:
        st.error("콘텐츠 데이터를 불러올 수 없어 재추천할 수 없습니다.")
        return
    
    all_contents = analysis['raw_contents']
    card_map = {str(c.get("card_id")): c for c in all_contents}

    # 피드백 기반 점수 조정
    scores_to_sort = adjust_scores_by_feedback(base_scores, all_candidates, card_map, feedback)
    
    # 새로운 추천 생성
    sorted_candidates = sorted(scores_to_sort.keys(), key=lambda cid: scores_to_sort.get(cid, 0.0), reverse=True)
    top_n = st.session_state.get('top_n', DEFAULT_CONFIG["top_n"])
    
    new_rec_ids = []
    for cid in sorted_candidates:
        if cid not in shown_ids:
            new_rec_ids.append(cid)
        if len(new_rec_ids) >= top_n:
            break
    
    if new_rec_ids:
        new_results = [card_map[cid] for cid in new_rec_ids if cid in card_map]
        for i, content in enumerate(new_results):
            content['recommendation_reason'] = f"새로운 추천: 이전 학습 내용과 피드백을 반영하여 추천되었습니다."
            content['recommendation_source'] = 'reranked'
            content['recommendation_rank'] = len(results) + i + 1
        
        st.session_state['shown_recommendations'].extend(new_results)
        st.rerun()
    else:
        st.info("더 이상 추천해드릴 새로운 콘텐츠가 없습니다. 😃")


def render_learning_history() -> None:
    """학습 히스토리 렌더링"""
    st.markdown('### 📚 나의 학습 히스토리')
    
    try:
        # 로거 모듈만 직접 로드 (안전한 방식)
        import os
        from pathlib import Path
        import importlib.util
        
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        logger_file_path = os.path.join(str(project_root), "contents", "recommendation", "user_contents_logger.py")
        
        # 파일 존재 확인
        if not os.path.exists(logger_file_path):
            st.warning("로거 파일을 찾을 수 없습니다.")
            return
        
        logger_spec = importlib.util.spec_from_file_location(
            "user_contents_logger",
            logger_file_path
        )
        if logger_spec is None or logger_spec.loader is None:
            st.warning("로거 모듈을 불러올 수 없습니다.")
            return
        
        logger_module = importlib.util.module_from_spec(logger_spec)
        logger_spec.loader.exec_module(logger_module)
        
        supabase_client = st.session_state.get("supabase")
        if not supabase_client:
            st.info("데이터베이스 연결이 필요합니다.")
            return
            
        logger = logger_module.get_logger(supabase_client)
        
        if logger:
            user_data = st.session_state.get('user_data', {})
            user_id = user_data.get('id', 'anonymous')
            
            if user_id != 'anonymous':
                history = logger.get_user_content_history(str(user_id), limit=10)
                
                if history:
                    st.markdown(f"**최근 확인한 콘텐츠 {len(history)}개**")
                    
                    for idx, log_item in enumerate(history[:5], 1):
                        with st.expander(f"{idx}. {log_item['content_title']} ({log_item['user_level']})", expanded=False):
                            col_hist1, col_hist2 = st.columns([3, 1])
                            
                            with col_hist1:
                                # AI 설명 표시
                                if log_item.get('ai_explanation'):
                                    st.markdown("**AI 설명:**")
                                    st.markdown(
                                        get_ai_explanation_style(log_item["ai_explanation"]),
                                        unsafe_allow_html=True
                                    )
                                
                                # 피드백 표시
                                if log_item.get('feedback_type'):
                                    emoji, text = get_feedback_display_info(log_item)
                                    st.success(f"{emoji} {text}으로 평가")
                            
                            with col_hist2:
                                st.markdown("**📊 상세 정보**")
                                formatted_time = format_datetime_string(log_item['viewed_at'])
                                st.write(f"조회 시간: {formatted_time}")
                else:
                    st.info("아직 조회한 콘텐츠가 없습니다. 맞춤 추천을 받아보세요!")
            else:
                st.info("로그인 후 학습 히스토리를 확인할 수 있습니다.")
        else:
            st.warning("로거를 초기화할 수 없습니다.")
            
    except Exception as e:
        st.warning("학습 히스토리를 불러올 수 없습니다.")
        st.error(f"오류 상세: {str(e)}")
        print(f"히스토리 로드 실패: {e}")


def render_learning_progress() -> None:
    """학습 현황 렌더링"""
    if 'recommendation_result' in st.session_state:
        st.divider()
        st.markdown('### 📊 현재 세션 학습 현황')
        
        rec_result = st.session_state['recommendation_result']
        if rec_result.get("success"):
            results = rec_result["results"]
            total_contents, explained_count, completion_rate = calculate_completion_rate(results, dict(st.session_state))
            
            # 메트릭 표시
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📚 추천받은 정보", f"{total_contents}개")
            with col2:
                st.metric("💡 내용을 확인한 정보", f"{explained_count}개")
            with col3:
                st.metric("✅ 학습 진행률", f"{completion_rate}%")
            
            # 진행도 바
            if total_contents > 0:
                progress = explained_count / total_contents
                st.progress(progress, text=f"오늘의 학습 진행: {int(progress*100)}%")
                
                if explained_count == total_contents:
                    st.success("🎉 오늘 추천받은 모든 정보의 설명을 확인했어요!")
                    st.toast("학습 완료!", icon="🎉")
                    st.markdown(get_celebration_style(), unsafe_allow_html=True)