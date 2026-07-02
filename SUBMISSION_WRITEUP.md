# Submission Write-Up — ZenTravel Concierge

---

## Problem Statement

Planning a trip is stressful: safety concerns, unpredictable weather, forgetting essential gear, and navigating advisory warnings. Travellers — especially solo or first-time international travellers — lack a unified, intelligent assistant that proactively surfaces safety risk information, adapts packing advice to real weather data, and pauses for human confirmation before proceeding with high-risk itineraries.

**ZenTravel Concierge** addresses this gap: a secure, multi-agent AI concierge that orchestrates travel safety checks, weather lookups, and personalised packing list generation — while keeping humans in the loop when destinations are flagged as dangerous.

---

## Solution Architecture

```
START ──▶ [security_checkpoint] ──blocked──▶ [security_event]
                │
              safe
                │
         [orchestrator]
          │           │
     AgentTool    AgentTool
          │           │
  [advisory_agent] [packing_agent]
   (MCP tools)     (MCP tools)
          │
   [check_advisory]
          │           │
    consent_needed   safe
          │           │
   [hitl_consent]  [final_response]
          │
   [final_response]
```

**MCP Server Tools:**
- `get_weather` — weather forecast for the destination
- `get_travel_advisory` — advisory safety level (LEVEL 1–4)
- `calculate_packing_essentials` — custom packing list by weather + duration

---

## Concepts Used

| Concept | Where Used |
|---------|-----------|
| **ADK Workflow** | `app/agent.py` — `Workflow(name=..., edges=[...])` |
| **LlmAgent** | `orchestrator`, `advisory_agent`, `packing_agent` in `app/agent.py` |
| **AgentTool** | `AgentTool(advisory_agent)` and `AgentTool(packing_agent)` wired into orchestrator |
| **ctx.state** | Advisory level persisted via `after_tool_callback` → `state["advisory_level"]` |
| **MCP Server** | `app/mcp_server.py` — FastMCP with `get_weather`, `get_travel_advisory`, `calculate_packing_essentials` |
| **MCPToolset** | Wired into both `advisory_agent` and `packing_agent` in `app/agent.py` |
| **Security Checkpoint** | `security_checkpoint` function node in `app/agent.py` |
| **Agents CLI** | Project scaffolded with `uvx google-agents-cli scaffold create`, playground via `make playground` |

---

## Security Design

| Control | Implementation | Why It Matters |
|---------|---------------|---------------|
| **PII Scrubbing** | Regex strips email addresses and passport numbers from user input before LLM sees them | Prevents sensitive personal data leaking into LLM prompts or logs |
| **Prompt Injection Detection** | Keywords like "ignore previous instructions", "override instructions" trigger a `blocked` route to `security_event` | Prevents adversarial hijacking of agent behaviour |
| **Structured Audit Log** | Every request emits a JSON audit log to stderr with `pii_detected`, `injection_detected`, and `severity` (INFO/WARNING/CRITICAL) | Provides traceability for security incidents |

---

## MCP Server Design

File: `app/mcp_server.py`

| Tool | Purpose |
|------|---------|
| `get_weather(city)` | Returns current weather forecast for a city; used by `packing_agent` to drive item selection |
| `get_travel_advisory(country)` | Returns LEVEL 1–4 advisory with warning text; used by `advisory_agent` to assess trip safety |
| `calculate_packing_essentials(weather_profile, duration_days)` | Compiles a packing list tailored to weather and trip length; used by `packing_agent` |

All tools exposed via FastMCP over stdio transport, auto-started by `McpToolset` when agents initialise.

---

## HITL Flow

When `advisory_agent` returns a **LEVEL 3 or LEVEL 4** advisory, the `check_advisory` node routes to the `hitl_consent` node, which yields a `RequestInput` pause asking the user:

> "⚠️ WARNING: The selected destination has a high safety risk (Level 3/4). Do you still wish to proceed? (Reply with 'yes' or 'no')"

- If the user replies **yes** → flow continues to `final_response` with the full plan
- If the user replies **no** → `final_response` returns a polite cancellation message

This ensures no high-risk trip itinerary is generated without explicit user consent.

---

## Demo Walkthrough

Refer to the 3 sample test cases in `README.md`:

1. **Safe Destination (Tokyo)** — Full plan generated with advisory, weather, and packing list
2. **Prompt Injection Blocked** — Security checkpoint intercepts and blocks the request
3. **High-Risk Destination (Syria) + HITL** — User asked to confirm before planning proceeds

---

## Impact / Value Statement

ZenTravel Concierge benefits:
- **Solo travellers and backpackers** who need consolidated safety + packing guidance
- **First-time international travellers** unfamiliar with government travel advisories
- **Travel agencies** looking to provide AI-assisted pre-trip briefings at scale

By combining real-time advisory data, weather-aware packing intelligence, and human oversight for dangerous destinations, ZenTravel Concierge makes travel planning safer, smarter, and more personal.
