from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from langchain.embeddings import OpenAIEmbeddings

from dotenv import load_dotenv
import os

load_dotenv()
embedding = OpenAIEmbeddings()
vectordb = Chroma(persist_directory="my_app/chat_bot/finance_qa_rag/vectorstore/chroma_db", embedding_function=embedding)
retriever = vectordb.as_retriever()
qa = RetrievalQA.from_chain_type(llm=OpenAI(), retriever=retriever)

def answer(query):
    return qa.run(query)

if __name__ == "__main__":
    q = input("질문: ")
    print("답변:", answer(q))