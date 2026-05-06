
from langchain_openai import ChatOpenAI
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

    
    while True:
        input_message = input("You: ").strip()
        if not input_message:
            continue

        if input_message == "STOP":
            print("結束掰掰")
            break
    
        ai_message =llm.invoke(input_message)
        print(ai_message.content)

    #agent_name = "河馬先生"
    #print(api_key)
    #print(f"我是{agent_name} 我是一顆蛋")

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

if __name__ == "__main__":
    main()
