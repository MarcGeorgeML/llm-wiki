import os
import groq
import json
import urllib.request


from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("MODEL", "gemma3:12b")


def ask_groq_stream(prompt: str, system: str = ""):
    client = groq.Groq(api_key=GROQ_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        max_completion_tokens=8192,
        stream=True,
    )
    for chunk in stream:
        text = chunk.choices[0].delta.content
        if text:
            yield text


def ask_ollama_stream(prompt: str, system: str = ""):
    payload = json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "system": system,
            "stream": True,
            "options": {"temperature": 0.0, "top_p": 1.0, "top_k": 1},
        }
    ).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            chunk = json.loads(line)
            if chunk.get("done"):
                break
            yield chunk["response"]
