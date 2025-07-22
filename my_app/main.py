from fastapi import FastAPI, Query
from my_app.chat_bot.finance_qa_rag.rag.rag_pipeline import answer

app = FastAPI()

@app.get("/ask")
def ask(query: str = Query(...)):
    try:
        result = answer(query)
        return {"query": query, "answer": result}
    except Exception as e:
        print(f"❗ answer 함수 내부 에러: {e}")
        return {"query": query, "answer": f"[ERROR] {str(e)}"}
