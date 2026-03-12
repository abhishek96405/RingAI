import inspect
from pipecat.services.google.gemini_live import GeminiLiveLLMService

print("=" * 70)
print("GeminiLiveLLMService — relevant methods")
print("=" * 70)

for name, method in inspect.getmembers(GeminiLiveLLMService, predicate=inspect.isfunction):
    if not name.startswith("__"):
        try:
            sig = inspect.signature(method)
        except (ValueError, TypeError):
            sig = "(?)"
        print(f"  {name}{sig}")