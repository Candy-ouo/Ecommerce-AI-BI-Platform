"""命令行 AI 对话 Demo —— 现在就能和百炼聊天"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm_client import get_llm_client

llm = get_llm_client()

print("=" * 50)
print("AI Chat - 输入消息开始对话，输入 quit 退出")
print("=" * 50)

messages = []  # 对话历史

while True:
    user_input = input("\nYou: ").strip()
    if not user_input:
        continue
    if user_input.lower() in ("quit", "exit", "q"):
        print("Bye!")
        break

    messages.append({"role": "user", "content": user_input})

    # 构建带历史的 prompt
    history_text = ""
    for m in messages[-10:]:  # 最近10轮
        role = "用户" if m["role"] == "user" else "AI"
        history_text += f"{role}: {m['content']}\n"

    prompt = f"以下是一段对话，请作为电商数据分析助手回答：\n\n{history_text}\nAI: "

    print("AI: ", end="", flush=True)
    full_response = ""
    for chunk in llm.chat_stream(prompt):
        print(chunk, end="", flush=True)
        full_response += chunk

    messages.append({"role": "assistant", "content": full_response})
    print()
