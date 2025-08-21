from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey

Base = declarative_base()

class Price(Base):
    __tablename__ = "prices"
    id = Column(Integer, primary_key=True, index=True)
    security_id = Column(String, index=True)   # ex. 'SMH'
    date = Column(Date, index=True)
    close = Column(Float)

class NewsArticle(Base):
    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True, index=True)
    security_id = Column(String, index=True)
    published_at = Column(Date)
    title = Column(String)
    summary = Column(String)  # 미리 OpenAI로 요약해 둔 텍스트

class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    security_id = Column(String, index=True)
    quiz_date = Column(Date)
    p0 = Column(Float)    # 3개월 전 종가
    p1 = Column(Float)    # 현재 종가
    actual_pct = Column(Float)
    option_a = Column(Float)
    option_b = Column(Float)
    option_c = Column(Float)
    option_d = Column(Float)
    selected_pct = Column(Float, nullable=True)
    error_pct = Column(Float, nullable=True)
    skill_score = Column(Float, nullable=True)
    is_correct = Column(Integer, nullable=True)  # 0 or 1