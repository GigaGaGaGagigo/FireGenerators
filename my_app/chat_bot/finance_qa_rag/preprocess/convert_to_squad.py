# convert_to_squad.py
import json

def convert_to_squad_format(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    squad_data = {"data": []}
    for i, d in enumerate(data):
        squad_data["data"].append({
            "title": d['term'],
            "paragraphs": [{
                "context": d['definition'],
                "qas": [{
                    "id": f"term-{i}",
                    "question": f"{d['term']}란?",
                    "answers": [{"text": d['definition'], "answer_start": 0}],
                    "is_impossible": False
                }]
            }]
        })
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(squad_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    convert_to_squad_format("my_app/chat_bot/finance_qa_rag/data/finance_terms.json", "my_app/chat_bot/finance_qa_rag/data/squad_terms.json")