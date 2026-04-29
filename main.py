
from langchain_openai import ChatOpenAI
import  os
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("OPENAI_API_KEY: 已設定")
    else:
        print("OPENAI_API_KEY: 未設定")
    return

load_dotenv()

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    print(api_key)
    #agent_name = "河馬先生"
    #print(api_key)
    #print(f"我是{agent_name} 我是一顆蛋")

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

if __name__ == "__main__":
    main()
