# Agentic Architecture & Extensibility

## Current Architecture

The agent is a **single-model, multi-tool loop**. One Gemini model instance orchestrates all capability by selecting from a fixed set of declared tools. The key properties that make this extensible:

1. **Tools are independent Python functions.** Each tool in `app/tools/` has no knowledge of the agent or other tools. Adding a new capability means writing one new function and one new `FunctionDeclaration`.

2. **The LLM handles routing.** There is no explicit intent classifier or routing table. Gemini reads the tool descriptions and decides which to call. A new tool becomes available to users the moment it is declared — no routing rules to update.

3. **Tool results are composable.** Because Gemini can call multiple tools in sequence within one response, tools naturally compose. A user asking "find me an ice maker part and tell me if it fits my fridge model" triggers `search_parts` followed by `check_compatibility` without any special orchestration code.

---

## Adding a New Tool (example: order status lookup)

**Step 1** — Write the function in `app/tools/order_status.py`:

```python
def get_order_status(order_id: str) -> dict:
    # Call your order management system API
    ...
```

**Step 2** — Add a `FunctionDeclaration` in `agent.py`:

```python
types.FunctionDeclaration(
    name="get_order_status",
    description="Look up the status of a customer order by order ID.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "order_id": types.Schema(type=types.Type.STRING, description="The order ID"),
        },
        required=["order_id"],
    ),
),
```

**Step 3** — Add a branch in `_run_tool`:

```python
if name == "get_order_status":
    return get_order_status(args["order_id"])
```

That's it. The agent immediately gains the ability to answer "where is my order #12345?" without any other changes.

---

## Adding a New Appliance Category (example: washing machines)

The scope enforcement is entirely in the system prompt (`SYSTEM_PROMPT` in `agent.py`). To add washing machines:

1. Update `SYSTEM_PROMPT` to include "washing machine" in the list of supported appliances
2. Run the scraper with new seed URLs for washing machine parts
3. Re-ingest to add washing machine parts/guides to ChromaDB

The `appliance_type` metadata field and filter in `search_parts` and `troubleshoot` already handle arbitrary appliance type strings — no tool code changes needed.

---

## Extending the Frontend

The frontend receives a structured `ChatResponse`:

```typescript
{
  role: "assistant",
  content: string,       // markdown text
  products: Product[]    // zero or more product cards
}
```

New rich UI elements (repair guide cards, compatibility matrices, order tracking widgets) can be added by:
1. Adding a new field to `ChatResponse` in `main.py`
2. Populating it in `_extract_*` in `agent.py`
3. Rendering the new component in `ChatWindow.tsx`

The data contract is the only coupling between frontend and backend.

---

## Current Limitations

| Limitation | Impact |
|---|---|
| No session persistence | Conversation history resets on page refresh; `session_id` is accepted but unused server-side |
| No user authentication | Any client can call `/api/chat`; no per-user rate limiting |
| Single-instance ChromaDB | Local file-based DB; cannot be shared across multiple backend instances |
| Synchronous Gemini SDK | Each request blocks a thread for the duration of the LLM call |
| 110 parts in DB | Coverage is limited to manually seeded URLs; not a full catalog |
