import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render_user_management():
    """사용자 관리"""
    st.subheader("👥 사용자 관리")
    
    # 샘플 사용자 데이터
    users_data = {
        'ID': [1, 2, 3, 4, 5],
        '이메일': [
            'user1@example.com',
            'user2@example.com', 
            'user3@example.com',
            'user4@example.com',
            'user5@example.com'
        ],
        '가입일': [
            '2024-01-15',
            '2024-02-20',
            '2024-03-10',
            '2024-04-05',
            '2024-05-12'
        ],
        '역할': ['User', 'User', 'Admin', 'User', 'User'],
        '상태': ['활성', '활성', '활성', '비활성', '활성'],
        '최종 로그인': [
            '2024-08-07',
            '2024-08-06',
            '2024-08-07',
            '2024-07-20',
            '2024-08-05'
        ]
    }
    
    users_df = pd.DataFrame(users_data)
    
    # 필터링 옵션
    col1, col2, col3 = st.columns(3)
    
    with col1:
        role_filter = st.selectbox("역할 필터", ['전체', 'User', 'Admin'])
    
    with col2:
        status_filter = st.selectbox("상태 필터", ['전체', '활성', '비활성'])
    
    with col3:
        if st.button("새 사용자 추가"):
            st.info("새 사용자 추가 모달을 준비 중입니다.")
    
    # 필터 적용
    filtered_df = users_df.copy()
    if role_filter != '전체':
        filtered_df = filtered_df[filtered_df['역할'] == role_filter]
    if status_filter != '전체':
        filtered_df = filtered_df[filtered_df['상태'] == status_filter]
    
    # 사용자 테이블
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    # 사용자 통계
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("전체 사용자", len(users_df))
    
    with col2:
        active_users = len(users_df[users_df['상태'] == '활성'])
        st.metric("활성 사용자", active_users)
    
    with col3:
        admin_users = len(users_df[users_df['역할'] == 'Admin'])
        st.metric("관리자", admin_users)
    
    with col4:
        new_users_today = 1  # 샘플 데이터
        st.metric("오늘 신규", new_users_today)

def render_system_monitoring():
    """시스템 모니터링"""
    st.subheader("🖥️ 시스템 모니터링")
    
    # 시스템 상태
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "서버 상태",
            "정상",
            delta="99.9% 가동률",
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            "CPU 사용률",
            "45%",
            delta="-5%",
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "메모리 사용률", 
            "62%",
            delta="+3%",
            delta_color="normal"
        )
    
    with col4:
        st.metric(
            "디스크 사용률",
            "78%",
            delta="+2%",
            delta_color="normal"
        )
    
    # 에러 로그
    st.subheader("🚨 최근 에러 로그")
    
    error_logs = pd.DataFrame({
        '시간': [
            '2024-08-07 14:30:25',
            '2024-08-07 12:15:10',
            '2024-08-07 09:45:33',
            '2024-08-06 16:20:15'
        ],
        '레벨': ['WARNING', 'ERROR', 'INFO', 'ERROR'],
        '메시지': [
            'API 응답 시간 증가 감지',
            '데이터베이스 연결 실패',
            '사용자 로그인 성공',
            '외부 API 호출 실패'
        ],
        '모듈': ['API', 'DATABASE', 'AUTH', 'EXTERNAL']
    })
    
    st.dataframe(error_logs, use_container_width=True, hide_index=True)

def render_content_management():
    """콘텐츠 관리"""
    st.subheader("📝 콘텐츠 관리")
    
    # 탭으로 구분
    tab1, tab2, tab3 = st.tabs(["퀴즈 관리", "콘텐츠 관리", "공지사항"])
    
    with tab1:
        st.write("**퀴즈 관리**")
        
        if st.button("새 퀴즈 추가"):
            st.info("퀴즈 생성 모달을 준비 중입니다.")
        
        # 퀴즈 목록
        quiz_data = {
            'ID': [1, 2, 3],
            '제목': ['FIRE 기본 개념', 'ETF 투자 전략', '리밸런싱 방법'],
            '카테고리': ['기초', '중급', '고급'],
            '생성일': ['2024-08-01', '2024-08-03', '2024-08-05'],
            '상태': ['활성', '활성', '비활성']
        }
        
        st.dataframe(pd.DataFrame(quiz_data), use_container_width=True, hide_index=True)
    
    with tab2:
        st.write("**오늘의 콘텐츠 관리**")
        
        content_type = st.selectbox("콘텐츠 유형", ["기사", "동영상", "팟캐스트", "인포그래픽"])
        content_title = st.text_input("제목")
        content_summary = st.text_area("요약")
        content_url = st.text_input("URL")
        
        if st.button("콘텐츠 추가"):
            st.success("콘텐츠가 추가되었습니다!")
    
    with tab3:
        st.write("**공지사항 관리**")
        
        notice_title = st.text_input("공지 제목")
        notice_content = st.text_area("공지 내용", height=200)
        notice_important = st.checkbox("중요 공지")
        
        if st.button("공지사항 게시"):
            st.success("공지사항이 게시되었습니다!")

def render(page_type):
    """관리자 페이지 렌더링"""
    if page_type == "admin1":
        st.title("👥 사용자 및 시스템 관리")
        
        render_user_management()
        st.divider()
        render_system_monitoring()
        
    elif page_type == "admin2":
        st.title("📝 콘텐츠 및 서비스 관리")
        
        render_content_management()
        
        st.divider()
        
        # 설정 관리
        st.subheader("⚙️ 시스템 설정")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.checkbox("신규 회원가입 허용", value=True)
            st.checkbox("점검 모드", value=False)
            st.number_input("최대 동시 접속자", min_value=100, max_value=10000, value=1000)
        
        with col2:
            st.checkbox("이메일 알림 발송", value=True)
            st.checkbox("자동 백업", value=True)
            st.selectbox("로그 레벨", ["DEBUG", "INFO", "WARNING", "ERROR"], index=1)
        
        if st.button("설정 저장"):
            st.success("시스템 설정이 저장되었습니다!")