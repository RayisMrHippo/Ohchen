
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import  os
from dotenv import load_dotenv

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("OPENAI_API_KEY: 已設定")
    else:
        print("OPENAI_API_KEY: 未設定")
        return

    model_name = os.getenv("MODEL_NAME")
    if model_name:
        print("MODEL_NAME: 已設定")
    else:
        print("MODEL_NAME: 未設定")
        return

    base_url = os.getenv("BASE_URL")
    if base_url:
        print("BASE_URL: 已設定")
    else:
        print("BASE_URL: 未設定")
        return
   
    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key
    )

    messages = []
    
    while True:
        input_message = input("You: ").strip()
        if not input_message:
            continue
        
        human_message = HumanMessage(content=input_message)
        context_messages =[*messages, human_message]

        print("助手：", end="", flush=True)
        reply_parts: list[str] = []
        for chunk in llm.stream(context_messages):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                reply_parts.append(chunk.content)
        print()

        assistant_text = "".join(reply_parts)
        assistant_message = AIMessage(content=assistant_text)

        messages.append(human_message)
        messages.append(assistant_message)

        if input_message == "STOP":
            print("結束掰掰")
            break
    
        ai_message =llm.invoke(input_message)
        print(ai_message.content)

        for chunk in llm.stream(input_message):
            print(chunk.content, end="", flush=True)

        messages.append(human_message)
        messages.append(assistant_message)

        

    #agent_name = "河馬先生"
    #print(api_key)
    #print(f"我是{agent_name} 我是一顆蛋")

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

if __name__ == "__main__":
    main()
