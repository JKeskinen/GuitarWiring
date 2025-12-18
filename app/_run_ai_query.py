import sys
import pathlib
# Ensure repo root is on sys.path so `import app...` works when running this script
repo_root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from app.ai_assistant import AIAssistant

q = "I'm on step 1. Can you explain in more detail what I need to do and provide specific tips?"
print(f"User question: {q}\n")

assistant = AIAssistant()
try:
    import re
    m = re.search(r"i\'??m on step\s*(\d+)", q, re.I)
    if m:
        step_n = int(m.group(1))
        print('Local step guidance (no LLM call):\n')
        print(assistant.get_step_guidance(step_n))
        raise SystemExit(0)

    is_easter, prompt_or_resp = assistant.build_context_prompt(q, 1)
    if is_easter:
        print('Easter-egg response (no AI call):\n')
        print(prompt_or_resp)
    else:
        print('Prompt sent to AI (context):\n')
        print(prompt_or_resp)
        print('\nAI response:\n')
        for chunk in assistant.stream_response(prompt_or_resp, timeout=10.0):
            print(chunk, end='', flush=True)
        print('\n')
except Exception as e:
    print('Error running assistant:', e)
