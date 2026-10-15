"""Test Gemini — retry on 503"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.5-flash").strip()


def main():
    print("=" * 50)
    print("  Gemini Test (retry on 503)")
    print("=" * 50)

    if not KEY:
        print("ERROR: GEMINI_API_KEY kosong")
        return False

    print(f"Key OK (panjang {len(KEY)})")
    print(f"Model: {MODEL}")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=KEY)

    # List available models dulu
    print("\n--- Model yang tersedia di akun kamu ---")
    try:
        for m in client.models.list():
            name = getattr(m, "name", str(m))
            if "gemini" in name.lower():
                print(f"  {name}")
    except Exception as e:
        print(f"  (gagal list models: {e})")

    # Retry generate
    print(f"\n--- Coba generate dengan {MODEL} ---")
    for attempt in range(1, 6):
        try:
            print(f"Attempt {attempt}/5 ...")
            response = client.models.generate_content(
                model=MODEL,
                contents="Jawab 1 kalimat bahasa Indonesia: apa kabar?",
                config=types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=80,
                ),
            )
            text = getattr(response, "text", None) or "(empty)"
            print(f"\nBERHASIL!")
            print(f"Jawaban: {text}")
            return True
        except Exception as e:
            err = str(e)
            print(f"  Gagal: {e}")
            if "503" in err or "UNAVAILABLE" in err or "high demand" in err.lower():
                wait = attempt * 3
                print(f"  Server sibuk, tunggu {wait}s...")
                time.sleep(wait)
                continue
            break

    print("\nMasih gagal. Coba lagi 1-2 menit kemudian (server Gemini lagi padat).")
    return False


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)