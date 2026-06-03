
import os

def read_context(file_path):
    """
    讀取指定的檔案內容，作為 Agent 的 Extra Context。
    """
    # 轉換為絕對路徑，確保能找到檔案
    full_path = os.path.abspath(file_path)
    
    if not os.path.exists(full_path):
        return f"錯誤：找不到檔案 {file_path}"
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"--- 成功讀取內容 ---\n{content}\n--- 內容結束 ---"
    except Exception as e:
        return f"讀取檔案時發生錯誤: {str(e)}"

if __name__ == "__main__":
    # 這裡預設讀取 workspace 下的 practice_one.txt
    # 你可以根據實際情況修改路徑
    target_file = "studio_shell/workspace/practice_one.txt"
    print(read_context(target_file))
