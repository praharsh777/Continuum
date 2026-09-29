import sys, os, time, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from dotenv import load_dotenv; load_dotenv()
from agent.memory import default_memory_manager
from groq import Groq

t0 = time.time()
r = default_memory_manager.recall_similar_postmortems('payment timeout connection pool', 'payment-gateway', top_n=5)
print(f'Hindsight recall: {time.time()-t0:.2f}s, {len(r)} results')

g = Groq(api_key=os.getenv('GROQ_API_KEY'))
t1 = time.time()
msg = [{"role": "user", "content": "Respond only with valid JSON: {\"status\": \"ok\"}"}]
resp = g.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=msg,
    response_format={"type": "json_object"},
    temperature=0.1
)
t_groq = time.time() - t1
print(f"Groq call only: {t_groq:.2f}s")
print(f"Total sequential: {t_recall + t_groq:.2f}s")
