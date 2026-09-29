import os
import sys
from dotenv import load_dotenv

load_dotenv()

hindsight_key = os.getenv("HINDSIGHT_API_KEY")
hindsight_url = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
bank_id = os.getenv("HINDSIGHT_BANK_ID", "continuum-demo")
groq_key = os.getenv("GROQ_API_KEY")

print(f"Testing connections...")
print(f"Hindsight URL: {hindsight_url}")
print(f"Bank ID: {bank_id}")

# 1. Test Hindsight Client
print("\n--- 1. Testing Hindsight Cloud ---")
try:
    from hindsight_client import Hindsight
    client = Hindsight(base_url=hindsight_url, api_key=hindsight_key)
    
    # Try retaining a test memory
    print("Sending test retain...")
    retain_res = client.retain(
        bank_id=bank_id,
        content="Continuum agent verified system connection successfully.",
        context="verification_test",
        document_id="TEST-000",
        metadata={"test": "true"}
    )
    print(f"Retain Success! Response: {retain_res}")
    
    # Try recalling
    print("Sending test recall...")
    recall_res = client.recall(
        bank_id=bank_id,
        query="Continuum agent verification"
    )
    print(f"Recall Success! Found {len(recall_res.results)} results:")
    for r in recall_res.results:
        print(f" - [{r.id}] (doc: {r.document_id}): {r.text[:80]}")
except Exception as e:
    print(f"Hindsight Error: {type(e).__name__}: {e}")
    sys.exit(1)

# 2. Test Groq Client
print("\n--- 2. Testing Groq API ---")
try:
    from groq import Groq
    groq_client = Groq(api_key=groq_key)
    
    # Check primary model
    primary_model = os.getenv("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
    print(f"Testing primary model: {primary_model}...")
    try:
        completion = groq_client.chat.completions.create(
            model=primary_model,
            messages=[{"role": "user", "content": "Respond with JSON: {\"status\": \"ok\"}"}],
            response_format={"type": "json_object"}
        )
        print(f"Primary model response: {completion.choices[0].message.content}")
    except Exception as e:
        print(f"Primary model failed ({e}), testing fallback...")
        fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
        completion = groq_client.chat.completions.create(
            model=fallback_model,
            messages=[{"role": "user", "content": "Respond with JSON: {\"status\": \"ok\"}"}],
            response_format={"type": "json_object"}
        )
        print(f"Fallback model ({fallback_model}) response: {completion.choices[0].message.content}")
except Exception as e:
    print(f"Groq Error: {type(e).__name__}: {e}")
    sys.exit(1)

print("\nALL CONNECTIONS VERIFIED SUCCESSFULLY!")
