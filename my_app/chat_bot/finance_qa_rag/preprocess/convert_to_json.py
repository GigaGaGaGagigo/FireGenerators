import pandas as pd
import json

input_path = 'my_app/chat_bot/finance_qa_rag/data/통계용어사전.xlsx'
output_path = 'my_app/chat_bot/finance_qa_rag/data/finance_terms.json'

df = pd.read_excel(input_path)
terms = []

for _, row in df.iterrows():
    terms.append({
        "term": str(row['용어']).strip(),
        "definition": str(row['설명']).strip()
    })

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(terms, f, ensure_ascii=False, indent=2)

print(f"Saved to {output_path}")