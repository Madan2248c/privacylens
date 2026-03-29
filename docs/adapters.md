# Adapters

Adapters wrap LLM clients so PII masking happens transparently. Pass your client to `shield()` and use it exactly as before.

## Python adapters

### OpenAI

```python
from privacylens import shield
import openai

client = shield(openai.OpenAI())

# Sync
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "My email is john@example.com"}],
)

# Async
async_client = shield(openai.AsyncOpenAI())
response = await async_client.chat.completions.create(...)

# Streaming
stream = client.chat.completions.create(..., stream=True)
for chunk in stream:
    print(chunk.choices[0].delta.content, end="")
```

**What gets masked:** all `content` fields in `messages[]`.
**What gets restored:** `choices[].message.content` and streaming `delta.content`.

---

### Anthropic

```python
from privacylens import shield
import anthropic

client = shield(anthropic.Anthropic())

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "My SSN is 123-45-6789"}],
)

# Async — wrap AsyncAnthropic; use messages.create() (same method name)
async_client = shield(anthropic.AsyncAnthropic())
response = await async_client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "My SSN is 123-45-6789"}],
)
```

**What gets masked:** `content` in each message.
**What gets restored:** `content[].text` blocks in the response.

---

### LangChain

The LangChain adapter is a `BaseCallbackHandler`. `shield()` detects any `BaseChatModel` instance and returns a handler — pass it in the `callbacks` list of any LangChain LLM or chain.

```python
from privacylens import shield
from langchain_openai import ChatOpenAI

llm = ChatOpenAI()
handler = shield(llm)  # returns a LangChainCallbackHandler

# Pass the handler in callbacks — use your original llm as normal
response = llm.invoke(
    "My name is John Doe, email john@example.com",
    config={"callbacks": [handler]},
)

# Or pass directly to any chain
chain = prompt | llm
response = chain.invoke({"input": "..."}, config={"callbacks": [handler]})
```

**What gets masked:** prompts passed to `on_llm_start`.
**What gets restored:** generated text in `on_llm_end`.

---

### CrewAI

`CrewAIAdapter` wraps any callable with the signature `(messages: list[dict], **kwargs) -> str`. Pass your LLM callable to `shield()`:

```python
from privacylens import shield

# Any callable that accepts (messages, **kwargs) -> str
def my_llm(messages, **kwargs):
    ...

shielded_llm = shield(my_llm)  # Note: shield() auto-detects by isinstance checks;
                                # for raw callables use CrewAIAdapter directly:

from privacylens.adapters.crewai import CrewAIAdapter
from privacylens.core.pipeline import Pipeline
from privacylens.core.config import load_config

pipeline = Pipeline(load_config())
shielded_llm = CrewAIAdapter(my_llm, pipeline)

from crewai import Agent
agent = Agent(role="Analyst", goal="Summarize data", llm=shielded_llm)
```

---

### Amazon Strands

```python
from privacylens import shield
from strands import Agent
from strands.models import BedrockModel

model = shield(BedrockModel(model_id="anthropic.claude-3-5-haiku-20241022-v1:0"))

agent = Agent(model=model)
response = agent("Summarize the ticket for john@example.com")
```

---

## TypeScript adapters

### OpenAI

```typescript
import OpenAI from "openai";
import { shield } from "privacylens";

const client = shield(new OpenAI());

// Non-streaming
const response = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "My email is john@example.com" }],
});

// Streaming
const stream = await client.chat.completions.create({
  model: "gpt-4o-mini",
  stream: true,
  messages: [{ role: "user", content: "My phone is 555-123-4567" }],
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
```

`shield()` also works with `AzureOpenAI`:

```typescript
import { AzureOpenAI } from "openai";
const client = shield(new AzureOpenAI({ /* ... */ }));
```

To pass custom config, provide a `Partial<Config>` as the second argument:

```typescript
const client = shield(new OpenAI(), { vault: "memory" });
```

---

### Vercel AI SDK

```typescript
import { openai } from "@ai-sdk/openai";
import { generateText, streamText } from "ai";
import { shield } from "privacylens";

// generateText
const { text } = await generateText({
  model: shield(openai("gpt-4o-mini")),
  prompt: "Summarise the contract for john@example.com",
});

// streamText
const result = await streamText({
  model: shield(openai("gpt-4o-mini")),
  prompt: "Draft a reply to sarah@corp.io",
});
for await (const chunk of result.textStream) {
  process.stdout.write(chunk);
}
```

---

## Auto-detection

`shield()` inspects the client type and picks the right adapter automatically.

### Python

| Client type | Adapter returned |
|-------------|-----------------|
| `openai.OpenAI` | `OpenAIAdapter` (sync) |
| `openai.AsyncOpenAI` | `OpenAIAdapter` (async) |
| `anthropic.Anthropic` | `AnthropicAdapter` (sync) |
| `anthropic.AsyncAnthropic` | `AnthropicAdapter` (async) |
| `langchain_core.language_models.BaseChatModel` | `LangChainCallbackHandler` |
| `strands.models.Model` | `StrandsModelWrapper` |

For CrewAI, use `CrewAIAdapter` directly (see above) — `shield()` does not auto-detect raw callables.

### TypeScript

| Constructor name | Adapter returned |
|-----------------|-----------------|
| `OpenAI` | OpenAI proxy |
| `AzureOpenAI` | OpenAI proxy |
| `AsyncOpenAI` | OpenAI proxy (async) |

If the client type is not recognised, `shield()` raises a `TypeError` listing the supported types.
