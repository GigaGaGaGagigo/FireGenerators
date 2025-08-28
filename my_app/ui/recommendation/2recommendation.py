import streamlit as st
from utils.data_loader import fetch_company_news_rss, fetch_financial_summary

st.title("🔍 뉴스 + 재무 요약 검색")

query = st.text_input("검색할 회사명 또는 종목코드 입력", "")

if query:
    # 1) 뉴스 검색
    news_list = fetch_company_news_rss(query, top_n=5, hl='ko', gl='KR')

    # 2) 재무 요약 (티커면 바로 가능, 회사명이면 매핑 필요)
    fin_summary = fetch_financial_summary(query.upper())  # 종목코드로 가정

    # 뉴스 출력
    if news_list:
        st.subheader(f"📰 '{query}' 관련 뉴스")
        for news in news_list:
            st.write(f"**{news.get('title')}**")
            st.write(news.get("published"))
            st.markdown(f"[기사 보기]({news.get('link')})")
            st.markdown("---")
    else:
        st.warning("관련 뉴스를 찾지 못했습니다.")

    # 재무 요약 출력
    if fin_summary:
        st.subheader(f"📊 {query} 재무 요약")
        
        # 1) 영문 필드명 → 한글 레이블 매핑
        LABEL_KO = {
            "ticker":       "티커",
            "longName":     "회사명",
            "sector":       "섹터",
            "industry":     "업종",
            "marketCap":    "시가총액",
            "trailingPE":   "과거 PER",
            "forwardPE":    "예상 PER",
            "dividendYield":"배당수익률",
            "shortRatio":   "공매도 비율",
            "lastPrice":    "현재가",
            "changePct":    "변동률",
        }

        # 2) 한글 레이블 + 숫자 포맷팅 적용
        rows = []
        for key, value in fin_summary.items():
            label = LABEL_KO.get(key, key)  # 매핑이 없으면 영문 키 유지

            if value is None:
                formatted = "-"
            else:
            # 숫자/단위 포맷 예시
                if key == "marketCap":
                    formatted = f"{value:,.0f} 원"
                elif key in ("trailingPE", "forwardPE"):
                    formatted = f"{value:.2f} 배"
                elif key in ("dividendYield", "changePct"):
                    formatted = f"{value:.2f} %"
                elif key == "lastPrice":
                    formatted = f"{value:,.2f} USD"
                else:
                    formatted = value

            rows.append({"항목": label, "값": formatted})

        # 3) 테이블로 보기
        st.table(rows)

    else:
        st.warning("재무 요약 정보를 찾지 못했습니다.")