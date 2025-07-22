import os
import json
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings  
from langchain_community.vectorstores import Chroma  

load_dotenv()

with open("my_app/chat_bot/finance_qa_rag/data/finance_terms.json", encoding="utf-8") as f:
    data = json.load(f)

docs = [f"{item['term']}: {item['definition']}" for item in data]

splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=30)
texts = splitter.create_documents(docs)

embeddings = OpenAIEmbeddings()
Chroma.from_documents(texts, embedding=embeddings, persist_directory="my_app/chat_bot/finance_qa_rag/vectorstore/chroma_db")
