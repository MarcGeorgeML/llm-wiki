import os
from groq import Groq
import json
import urllib.request
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("MODEL", "gemma3:12b")


def ask_groq_stream(prompt: str):
    
    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user", 
                "content": prompt
            }
        ],
        temperature=0.2, # 0.2
        max_completion_tokens=8192,
        top_p=1,
        stream=True,
        stop=None
    )
    for chunk in completion:
        text = chunk.choices[0].delta.content
        if text:
            yield text


def ask_ollama_stream(prompt: str):
    payload = json.dumps({"model": MODEL, "prompt": prompt, "stream": True}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            chunk = json.loads(line)
            yield chunk["response"]
            if chunk.get("done"):
                break