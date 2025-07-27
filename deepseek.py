import requests
import subprocess
import psutil

OLLAMA_PATH = r"C:\Users\Admin\AppData\Local\Programs\Ollama\ollama.exe"
ollama_proc = None

#start background process
def start_ollama():
    global ollama_proc
    try:
        ollama_proc = subprocess.Popen(
            [OLLAMA_PATH, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        print("Ollama started!")
    except Exception as e:
        print(f"[ERROR] Failed to start Ollama: {e}")

def stop_ollama():
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] == "ollama.exe":
                print("Terminating ollama.exe...")
                proc.terminate()
                proc.wait(timeout=5)
                print("[INFO] ollama.exe terminated.")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired) as e:
            print(f"[WARNING] Could not terminate process: {e}")

def ask_deepseek(messages, model="deepseek-llm:7b"): #deepseek-r1:1.5b
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False
        }
    )
    return response.json()["message"]["content"]

def translate_with_deepseek(self, text):
        try:
            messages = [
                {"role": "system", "content": "You are a translation tool. Translate the following English text to Japanese without conversationally replying back to the text"},
                {"role": "user", "content": text}
            ]
            translation = ask_deepseek(messages)
            if "ですか" in text and "?" not in translation:
                translation = translation.replace(".", "?")
            return translation
            return translation
        except Exception as e:
            return f"[ERROR] Translation failed: {e}"
