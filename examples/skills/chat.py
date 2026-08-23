"""Interactive Skills Chat — terminal REPL demo.

Start the chat:
    python examples/skills/chat.py

The agent will load the appropriate skill based on what you type:
  - "review my code / find bugs"          → code-review skill
  - "analyse this data / statistics"      → data-analysis skill
  - "help me write / proofread this"      → writing-assistant skill
  - "humanize this / sounds too AI"       → humanizer skill
  - "quit" / "exit" / Ctrl-C             → exit
"""

from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from alcyoneus.core.graph import Agent, StateGraph
from alcyoneus.core.skills import SkillConfig
from alcyoneus.core.state import AgentState, Message
from alcyoneus.core.state.message_context_manager import MessageContextManager
from alcyoneus.utils.constants import END


load_dotenv()

SKILLS_DIR = str(Path(__file__).parent / "skills")


# ── Custom Tools ───────────────────────────────────────────────────────────


def get_weather(location: str) -> str:
    """Get the current weather for a location.

    Args:
        location: The city or location to get weather for

    Returns:
        A string describing the current weather
    """
    # Mock weather data
    weather_data = {
        "london": "Cloudy, 15°C",
        "new york": "Sunny, 22°C",
        "newyork": "Sunny, 22°C",
        "tokyo": "Rainy, 18°C",
        "paris": "Partly cloudy, 17°C",
    }

    location_lower = location.lower()
    if location_lower in weather_data:
        return f"The weather in {location} is: {weather_data[location_lower]}"
    return f"Weather data not available for {location}. Try London, New York, Tokyo, or Paris."


# ── Graph setup ────────────────────────────────────────────────────────────

agent = Agent(
    model="google/gemini-2.5-flash",
    system_prompt=[
        {
            "role": "system",
            "content": (
                "You are a smart, multi-skilled assistant.\n"
                "You have access to specialised skill modes that give you "
                "deeper expertise in specific domains.\n\n"
                "Rules for skill usage:\n"
                "1. When the user's request matches a skill, call set_skill() "
                "with that skill name to load its instructions.\n"
                "2. Skills are distinct — each one covers a specific domain. "
                "Use the available skills table to decide which one fits the request.\n"
                "3. The skill content will be returned directly — use it to guide your response.\n\n"
                "You also have a get_weather tool for weather queries."
            ),
        }
    ],
    tools=[get_weather],  # ← Add custom tools here
    skills=SkillConfig(
        skills_dir=SKILLS_DIR,
        inject_trigger_table=True,
        hot_reload=True,
    ),
    trim_context=True,
)

tool_node = agent.get_tool_node()


def should_use_tools(state: AgentState) -> str:
    if not state.context:
        return END
    last = state.context[-1]
    if last.role == "assistant" and hasattr(last, "tools_calls") and last.tools_calls:
        return "TOOL"
    if last.role == "tool":
        return "MAIN"
    return END


graph = StateGraph(context_manager=MessageContextManager(max_messages=20))
graph.add_node("MAIN", agent)
graph.add_node("TOOL", tool_node)
graph.add_conditional_edges("MAIN", should_use_tools, {"TOOL": "TOOL", END: END})
graph.add_edge("TOOL", "MAIN")
graph.set_entry_point("MAIN")

app = graph.compile()


# ── Helpers ────────────────────────────────────────────────────────────────


def print_banner(thread_id: str) -> None:
    skills = agent._skills_registry.get_all()  # type: ignore[union-attr]
    width = 54
    print("\n" + "=" * width)
    print("  Alcyoneus OS Skills — Interactive Chat")
    print("=" * width)
    if skills:
        print("Available skills:")
        for s in skills:
            triggers = "; ".join(f'"{t}"' for t in s.triggers[:2])
            print(f"  • {s.name:<22} → {triggers}")
    print()
    print(f"  Thread : {thread_id}")
    print("  Exit   : type 'quit', 'exit', or press Ctrl-C")
    print("=" * width + "\n")


# ── REPL ───────────────────────────────────────────────────────────────────


def main() -> None:
    thread_id = f"skills-chat-{uuid4().hex[:8]}"

    print_banner(thread_id)

    while True:
        prompt = "You: "
        try:
            user_input = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "bye"}:
            print("Goodbye!")
            break

        try:
            result = app.invoke(
                {"messages": [Message.text_message(user_input)]},
                config={"thread_id": thread_id, "recursion_limit": 20},
            )
        except Exception as exc:
            print(f"\n  [error] {exc}\n")
            continue

        # Check if any skill was loaded (look for set_skill tool calls)
        for msg in result["messages"]:
            if msg.role == "tool":
                text = msg.text() or ""
                if text.startswith("## SKILL:"):
                    # Extract skill name from header
                    skill_line = text.split("\n")[0]
                    skill_name = skill_line.replace("## SKILL:", "").strip()
                    print(f"  >> Skill loaded: {skill_name}")

        # Print the last assistant response
        for msg in reversed(result["messages"]):
            if msg.role == "assistant" and msg.text():
                print(f"\nAssistant: {msg.text()}\n")
                break


if __name__ == "__main__":
    main()
