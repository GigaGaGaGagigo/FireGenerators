import streamlit as st

st.set_page_config(page_title='S&P500 RAG App', layout='wide')
st.title('S&P500 RAG App')
st.markdown('왼쪽 사이드바에서 Pages를 선택해 주세요.')
st.sidebar.success('Pages에 가서 1_📈_종목추천 또는 2_📊_종목상세 페이지를 선택하세요.')
