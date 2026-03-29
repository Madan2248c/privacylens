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

# Async
async_client = shield(anthropic.AsyncAnthropic())
response = await async_client.messages.acreate(...)
```

**What gets masked:** `content` in each message.
**What gets restored:** `content[].text` blocks in the response.

---

### LangChain

The LangChain adapter is a `BaseCallbackHandler`. Pass it in the `callbacks` list of any LangChain LLM or chain.

```python
from privacylens import shield
from langchain_openai import ChatOpenAI

handler = shield(ChatOpenAI())

# Use as a callback handler
llm = ChatOpenAI(callbacks=[handler])
response = llm.invoke("My name is John Doe, email john@example.com")

# Or pass directly to any chain
chain = prompt | llm
response = chain.invoke({"input": "..."}, config={"callbacks": [handler]})
```

**What gets masked:** prompts passed to `on_llm_start`.
**What gets restored:** generated text in `on_llm_end`.

---

### CrewAI

```python
from privacylens import shield
from crewai import Agent, LLM

llm = shield(LLM(model="gpt-4o-mini"))

agent = Agent(
    role="Analyst",
    goal="Summarize customer data",
    llm=llm,
)
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
const client = shield(new AzureOpenAI({ ... }));
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

`shield()` inspects the client's constructor name and picks the right adapter automatically:

| Constructor name | Adapter used |
|-----------------|-------------|
| `OpenAI`, `AzureOpenAI` | OpenAI adapter |
| `AsyncOpenAI` | Async OpenAI adapter |
| `Anthropic` | Anthropic adapter |
| `AsyncAnthropic` | Async Anthropic adapter |
| LangChain `BaseChatModel` | LangChain callback handler |
| Strands `Model` | Strands model wrapper |

If the client type is not recognised, `shield()` raises a `TypeError` listing the supported types.
