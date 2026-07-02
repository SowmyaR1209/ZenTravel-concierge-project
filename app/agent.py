import re
import os
import sys
import json
import datetime
from pydantic import BaseModel, Field
from typing import Any, AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.workflow import Workflow, START, FunctionNode
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.tools import BaseTool, ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.apps import App, ResumabilityConfig
from google.genai import types

from .config import config

# ── MCP Toolset ────────────────────────────────────────────────────────────────
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_path],
        )
    )
)

# ── Callback: save advisory level into session state ──────────────────────────
async def save_advisory_level(
    tool: BaseTool, args: dict, tool_context: ToolContext, tool_response: dict
) -> dict | None:
    if tool.name == "get_travel_advisory":
        lvl = tool_response.get("advisory_level", "LEVEL 1")
        tool_context.state["advisory_level"] = lvl
    return None

# ── Input Schema ───────────────────────────────────────────────────────────────
class TravelRequest(BaseModel):
    query: str = Field(description="The user's travel request or preferences.")

# ── Specialist Sub-Agents ──────────────────────────────────────────────────────
advisory_agent = LlmAgent(
    name="advisory_agent",
    model=config.model,
    instruction="""You are a travel advisory specialist.
Use the get_travel_advisory tool to look up the safety level for the user's destination country.
Return a clear summary of the advisory level and any warnings.
""",
    description="Looks up travel advisories and safety warnings for a destination country.",
    tools=[mcp_toolset],
    after_tool_callback=save_advisory_level,
)

packing_agent = LlmAgent(
    name="packing_agent",
    model=config.model,
    instruction="""You are a travel packing specialist.
Use the get_weather tool to find the weather at the destination.
Use the calculate_packing_essentials tool to build a packing list based on the weather and duration.
Return a clear, bulleted packing list.
""",
    description="Builds a packing list based on destination weather and trip duration.",
    tools=[mcp_toolset],
)

# ── Orchestrator ───────────────────────────────────────────────────────────────
orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the lead coordinator of ZenTravel Concierge.
Your job is to plan a complete travel brief for the user.
Always use the advisory_agent tool to check travel safety for the destination.
Always use the packing_agent tool to build a packing list.
Once you have results from both, compile a unified travel plan containing:
1. A day-by-day itinerary suggestion.
2. Travel safety advisory status.
3. A recommended packing list.
Be concise and friendly.
""",
    tools=[AgentTool(advisory_agent), AgentTool(packing_agent)],
    output_key="orchestrator_output",
)

# ── Workflow Function Nodes ───────────────────────────────────────────────────

def security_checkpoint(ctx: Context, node_input: TravelRequest) -> Event:
    """Security gate: PII scrubbing + prompt injection detection + audit log."""
    query = node_input.query
    scrubbed = query
    has_pii = False
    has_injection = False

    # PII: email addresses
    if re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', scrubbed):
        has_pii = True
        scrubbed = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
                          "[REDACTED_EMAIL]", scrubbed)

    # PII: passport numbers (9 alphanumeric chars)
    if re.search(r'\b[A-Z0-9]{9}\b', scrubbed, re.IGNORECASE):
        has_pii = True
        scrubbed = re.sub(r'\b[A-Z0-9]{9}\b', "[REDACTED_PASSPORT]",
                          scrubbed, flags=re.IGNORECASE)

    # Injection keywords
    injection_kws = [
        "ignore previous instructions",
        "system prompt",
        "override instructions",
        "you are now a",
    ]
    for kw in injection_kws:
        if kw in query.lower():
            has_injection = True
            break

    # Structured audit log
    audit = {
        "timestamp": datetime.datetime.now().isoformat(),
        "pii_detected": has_pii,
        "injection_detected": has_injection,
        "severity": "CRITICAL" if has_injection else ("WARNING" if has_pii else "INFO"),
    }
    sys.stderr.write(f"AUDIT_LOG: {json.dumps(audit)}\n")

    if has_injection:
        return Event(output="Security: Prompt injection detected.", route="blocked")

    return Event(output=scrubbed, route="safe", state={"user_query": scrubbed})


def security_event(ctx: Context, node_input: Any) -> Event:
    """Return a blocked-request message to the user."""
    msg = (
        "⛔ ZenTravel Security Alert: Your request was blocked because it contained "
        "a suspected prompt injection attempt. Please rephrase and try again."
    )
    return Event(
        output=msg,
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
    )


def check_advisory(ctx: Context, node_input: Any) -> Event:
    """Route to HITL if destination is Level 3 or 4, otherwise proceed."""
    lvl = ctx.state.get("advisory_level", "LEVEL 1")
    if lvl in ["LEVEL 3", "LEVEL 4"]:
        return Event(output=node_input, route="consent_needed")
    return Event(output=node_input, route="safe")


async def hitl_consent(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    """Human-in-the-loop: ask the user to confirm travel to a high-risk destination."""
    if not ctx.resume_inputs or "consent" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="consent",
            message=(
                "⚠️ WARNING: This destination has a HIGH safety risk (Level 3 or 4 advisory). "
                "Do you still wish to proceed with planning this trip? "
                "Reply with 'yes' to continue or 'no' to cancel."
            ),
        )
        return
    answer = str(ctx.resume_inputs.get("consent", "no")).lower().strip()
    yield Event(
        output="Consent recorded.",
        state={"user_consent": "yes" if answer in ("yes", "y") else "no"},
    )


def final_response(ctx: Context, node_input: Any) -> Event:
    """Emit the final travel plan or cancellation message to the UI."""
    if ctx.state.get("user_consent") == "no":
        msg = (
            "✈️ ZenTravel Concierge: Trip planning has been cancelled based on your "
            "decision not to travel to a high-risk destination. Stay safe!"
        )
        return Event(
            output=msg,
            content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
        )

    plan = ctx.state.get("orchestrator_output")
    if not plan:
        if isinstance(node_input, str):
            plan = node_input
        else:
            plan = "Your travel plan has been generated. Please see the agent response above."

    return Event(
        output=plan,
        content=types.Content(role="model", parts=[types.Part.from_text(text=str(plan))]),
    )


# ── Wrap async generator with rerun_on_resume=True for HITL ──────────────────
hitl_consent_node = FunctionNode(func=hitl_consent, rerun_on_resume=True)

# ── Workflow Graph ─────────────────────────────────────────────────────────────
# Use 2-tuple dict-based routing: (source, {"route": target}) for conditional edges.
# This avoids the 3-tuple format which is not supported in the installed ADK version.
edges = [
    (START, security_checkpoint),
    (security_checkpoint, {"blocked": security_event, "safe": orchestrator}),
    (orchestrator, check_advisory),
    (check_advisory, {"consent_needed": hitl_consent_node, "safe": final_response}),
    (hitl_consent_node, final_response),
]

root_agent = Workflow(
    name="zentravel_concierge",
    edges=edges,
    input_schema=TravelRequest,
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
