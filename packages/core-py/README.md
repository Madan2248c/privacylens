# PrivacyLens Python SDK

Transparent PII masking for LLM clients.

```python
from privacylens import shield
import openai

client = shield(openai.OpenAI())
```
