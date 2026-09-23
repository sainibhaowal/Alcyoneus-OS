"""Alcyoneus OS CLI - Command line interface for the Alcyoneus SDK."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from alcyoneus.core.graph import CompiledGraph, StateGraph
from alcyoneus.core.state import Message


console = Console()


# CLI Configuration
class CLIConfig:
    def __init__(self):
        self.config_path = Path.home() / ".alcyoneus" / "config.yaml"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self.config, f)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.save()


cli_config = CLIConfig()


def _get_version() -> str:
    """Dynamically resolve version from package metadata with fallback."""
    try:
        import importlib.metadata

        return importlib.metadata.version("alcyoneus")
    except Exception:
        return "1.2.0"


@click.group()
@click.version_option(version=_get_version(), package_name="alcyoneus", prog_name="alcyoneus")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, config: str | None, verbose: bool):
    """Alcyoneus OS - Multi-agent orchestration platform CLI."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if config:
        cli_config.config_path = Path(config)
        cli_config.config = cli_config._load_config()


# Graph commands
@cli.group()
def graph():
    """Graph management commands."""


@graph.command("create")
@click.argument("name")
@click.option(
    "--template", "-t", type=click.Choice(["react", "rag", "swarm", "supervisor"]), default="react"
)
@click.option("--output", "-o", type=click.Path(), help="Output directory")
def graph_create(name: str, template: str, output: str | None):
    """Create a new graph from template."""
    output_dir = Path(output) if output else Path.cwd() / name
    output_dir.mkdir(parents=True, exist_ok=True)

    templates = {
        "react": _get_react_template(),
        "rag": _get_rag_template(),
        "swarm": _get_swarm_template(),
        "supervisor": _get_supervisor_template(),
    }

    graph_code = templates[template].format(name=name)
    (output_dir / f"{name}.py").write_text(graph_code)

    # Create config
    config = {
        "graph": {"name": name, "template": template},
        "model": "gpt-4o-mini",
        "checkpoint": {"type": "memory"},
    }
    (output_dir / "config.yaml").write_text(yaml.dump(config))

    console.print(f"[green]Created graph '{name}' in {output_dir}[/green]")
    console.print(f"Run: [cyan]alcyoneus graph run {output_dir}/{name}.py[/cyan]")


@graph.command("run")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option("--input", "-i", "input_text", help="Input message")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
@click.option("--stream", "-s", is_flag=True, help="Stream output")
@click.option("--thread-id", help="Thread ID for checkpointing")
def graph_run(
    graph_file: str, input_text: str | None, config: str | None, stream: bool, thread_id: str | None
):
    """Run a graph."""
    asyncio.run(_run_graph_async(graph_file, input_text, config, stream, thread_id))


async def _run_graph_async(
    graph_file: str,
    input_text: str | None,
    config_path: str | None,
    stream: bool,
    thread_id: str | None,
):
    # Load graph module
    import importlib.util

    spec = importlib.util.spec_from_file_location("graph_module", graph_file)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    # Find compiled graph
    graph_obj = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, CompiledGraph):
            graph_obj = attr
            break

    if not graph_obj:
        console.print("[red]No CompiledGraph found in module[/red]")
        return

    # Prepare input
    if not input_text:
        input_text = click.prompt("Enter input message")

    input_data = {"messages": [Message.text_message(input_text)]}
    config_dict = {"thread_id": thread_id or "cli-session"}

    if stream:
        console.print("[bold]Streaming output:[/bold]")
        async for chunk in graph_obj.astream(input_data, config=config_dict):
            for node_name, output in chunk.items():  # type: ignore[attr-defined]
                console.print(f"[cyan]{node_name}:[/cyan] {output}")
    else:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}")
        ) as progress:
            task = progress.add_task("Running graph...", total=None)
            result = await graph_obj.ainvoke(input_data, config=config_dict)
            progress.update(task, completed=True)

        # Print result
        messages = result.get("messages", [])
        for msg in messages:
            console.print(f"[green]{msg.role}:[/green] {msg.content}")


@graph.command("visualize")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file (HTML)")
@click.option("--format", "-f", type=click.Choice(["mermaid", "graphviz", "html"]), default="html")
def graph_visualize(graph_file: str, output: str | None, format: str) -> None:  # noqa: A002
    """Visualize graph structure."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("graph_module", graph_file)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    graph_obj = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, CompiledGraph):
            graph_obj = attr
            break

    if not graph_obj:
        console.print("[red]No CompiledGraph found[/red]")
        return

    if format == "mermaid":
        mermaid = graph_obj.generate_graph(format="mermaid")
        console.print(Syntax(mermaid, "mermaid"))  # type: ignore[arg-type]
        if output:
            Path(output).write_text(mermaid)  # type: ignore[arg-type]
    elif format == "graphviz":
        dot = graph_obj.generate_graph(format="graphviz")
        console.print(Syntax(dot, "dot"))  # type: ignore[arg-type]
        if output:
            Path(output).write_text(dot)  # type: ignore[arg-type]
    else:
        html = graph_obj.generate_graph(format="html")
        if output:
            Path(output).write_text(html)  # type: ignore[arg-type]
            console.print(f"[green]Saved to {output}[/green]")
        else:
            # Open in browser
            import tempfile
            import webbrowser

            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
                f.write(html.encode())  # type: ignore[union-attr]
                webbrowser.open(f"file://{f.name}")


@graph.command("validate")
@click.argument("graph_file", type=click.Path(exists=True))
def graph_validate(graph_file: str):
    """Validate graph structure."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("graph_module", graph_file)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    graph_obj = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, (StateGraph, CompiledGraph)):
            graph_obj = attr
            break

    if not graph_obj:
        console.print("[red]No StateGraph or CompiledGraph found[/red]")
        return

    if isinstance(graph_obj, StateGraph):
        try:
            graph_obj.compile()
            console.print("[green]Graph compiles successfully[/green]")
        except Exception as e:
            console.print(f"[red]Compilation failed: {e}[/red]")
    else:
        console.print("[green]Graph is already compiled and valid[/green]")


@graph.command("inspect")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output inspection as JSON")
@click.option("--yaml", "as_yaml", is_flag=True, help="Output inspection as YAML")
def graph_inspect(graph_file: str, as_json: bool, as_yaml: bool) -> None:
    """Inspect nodes, edges, entrypoint, and handlers in a graph file."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("graph_module", graph_file)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    graph_obj: Any = None
    # Prioritize CompiledGraph if available in module
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, CompiledGraph):
            graph_obj = attr
            break
    if not graph_obj:
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, StateGraph):
                graph_obj = attr
                break

    if not graph_obj:
        console.print("[red]No StateGraph or CompiledGraph found in module[/red]")
        return

    is_compiled = isinstance(graph_obj, CompiledGraph)
    state_graph = graph_obj._state_graph if is_compiled else graph_obj  # type: ignore[attr-defined]

    node_names: list[str] = (
        [str(k) for k in state_graph.nodes.keys()] if hasattr(state_graph, "nodes") else []
    )
    edges_list: list[dict[str, str]] = [
        {"source": str(getattr(e, "source", "")), "target": str(getattr(e, "target", ""))}
        for e in getattr(state_graph, "edges", [])
    ]
    entry_point = getattr(state_graph, "entry_point", None)

    info: dict[str, Any] = {
        "file": str(graph_file),
        "type": "CompiledGraph" if is_compiled else "StateGraph",
        "entry_point": entry_point,
        "nodes": node_names,
        "node_count": len(node_names),
        "edges": edges_list,
        "edge_count": len(edges_list),
    }

    if as_json:
        click.echo(json.dumps(info, indent=2))
    elif as_yaml:
        click.echo(yaml.dump(info, sort_keys=False).strip())
    else:
        console.print(f"[bold cyan]Graph Inspection:[/bold cyan] {graph_file}")
        console.print(f"  • Type: [bold]{info['type']}[/bold]")
        console.print(f"  • Entry Point: [yellow]{info['entry_point'] or 'None'}[/yellow]")
        nodes_str = ", ".join(node_names) or "None"
        console.print(f"  • Nodes ({len(node_names)}): [green]{nodes_str}[/green]")
        console.print(f"  • Edges ({len(edges_list)}):")
        for edge_item in edges_list:
            console.print(f"      {edge_item['source']} ➔ {edge_item['target']}")


# Agent commands
@cli.group()
def agent():
    """Agent management commands."""


@agent.command("create")
@click.argument("name")
@click.option(
    "--type", "-t", "agent_type", type=click.Choice(["react", "rag", "swarm"]), default="react"
)
@click.option("--model", "-m", default="gpt-4o-mini")
@click.option("--output", "-o", type=click.Path())
def agent_create(name: str, agent_type: str, model: str, output: str | None):
    """Create a new agent."""
    output_dir = Path(output) if output else Path.cwd() / "agents" / name
    output_dir.mkdir(parents=True, exist_ok=True)

    template = _get_agent_template(agent_type)
    agent_code = template.format(name=name, model=model)
    (output_dir / f"{name}_agent.py").write_text(agent_code)

    console.print(f"[green]Created agent '{name}' in {output_dir}[/green]")


@agent.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--yaml", "as_yaml", is_flag=True, help="Output as YAML")
def agent_list(as_json: bool, as_yaml: bool):
    """List available agent types."""
    agents = [
        {"type": "react", "description": "Reasoning + Acting agent with tool use"},
        {
            "type": "plan-act-reflect",
            "description": "Autonomous planning, execution, reflection agent",
        },
        {"type": "rag", "description": "Retrieval-Augmented Generation agent"},
        {"type": "swarm", "description": "Multi-agent swarm coordination"},
        {"type": "supervisor", "description": "Supervisor team orchestration"},
        {"type": "structured", "description": "Structured output agent"},
    ]

    if as_json:
        click.echo(json.dumps(agents, indent=2))
    elif as_yaml:
        click.echo(yaml.dump(agents, sort_keys=False).strip())
    else:
        table = Table(title="Available Agent Types")
        table.add_column("Type", style="cyan")
        table.add_column("Description")
        for item in agents:
            table.add_row(item["type"], item["description"])
        console.print(table)


# Tool commands
@cli.group()
def tool():
    """Tool management commands."""


@tool.command("list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--yaml", "as_yaml", is_flag=True, help="Output as YAML")
def tool_list(category: str | None, as_json: bool, as_yaml: bool):
    """List available tools."""
    tools = [
        ("calculator", "math", "Basic calculator"),
        ("safe_calculator", "math", "Safe calculator with validation"),
        ("fetch_url", "web", "Fetch web content"),
        ("web_search", "web", "Multi-provider web search"),
        ("file_search", "files", "Semantic file search (RAG)"),
        ("generate_image", "image", "Image generation (DALL-E, Imagen, SDXL)"),
        ("shell", "system", "Shell command execution"),
        ("computer_use", "system", "GUI automation"),
        ("memory_tool", "memory", "Long-term memory"),
    ]

    filtered = [
        {"name": name, "category": cat, "description": desc}
        for name, cat, desc in tools
        if not category or cat == category
    ]

    if as_json:
        click.echo(json.dumps(filtered, indent=2))
    elif as_yaml:
        click.echo(yaml.dump(filtered, sort_keys=False).strip())
    else:
        table = Table(title="Available Tools")
        table.add_column("Name", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Description")
        for item in filtered:
            table.add_row(item["name"], item["category"], item["description"])
        console.print(table)


@tool.command("test")
@click.argument("tool_name")
@click.option("--args", "-a", help="JSON arguments")
def tool_test(tool_name: str, args: str | None):
    """Test a tool interactively."""
    # Import and test tool
    console.print(f"[yellow]Testing tool: {tool_name}[/yellow]")
    # Implementation would load and run tool


# Config commands
@cli.group()
def config():
    """Configuration management."""


@config.command("show")
def config_show():
    """Show current configuration."""
    console.print(Syntax(yaml.dump(cli_config.config), "yaml"))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set configuration value."""
    cli_config.set(key, value)
    console.print(f"[green]Set {key} = {value}[/green]")


@config.command("get")
@click.argument("key")
def config_get(key: str):
    """Get configuration value."""
    val = cli_config.get(key)
    if val is not None:
        console.print(val)
    else:
        console.print(f"[yellow]Key '{key}' not found[/yellow]")


# Deploy commands
@cli.group()
def deploy():
    """Deployment commands."""


@deploy.command("docker")
@click.option("--tag", "-t", default="alcyoneus/app:latest")
@click.option("--push", is_flag=True, help="Push to registry")
def deploy_docker(tag: str, push: bool):
    """Build Docker image."""
    import subprocess  # nosec: B404

    console.print(f"[bold]Building Docker image: {tag}[/bold]")
    result = subprocess.run(["docker", "build", "-t", tag, "-f", "deployment/Dockerfile", "."])  # noqa: S607
    if result.returncode == 0 and push:
        subprocess.run(["docker", "push", tag])  # noqa: S607


@deploy.command("helm")
@click.option("--release", "-r", default="alcyoneus")
@click.option("--namespace", "-n", default="default")
@click.option("--values", "-f", multiple=True, help="Values files")
def deploy_helm(release: str, namespace: str, values: tuple):
    """Deploy with Helm."""
    import subprocess  # nosec: B404

    cmd = ["helm", "upgrade", "--install", release, "deployment/helm/alcyoneus", "-n", namespace]
    for v in values:
        cmd.extend(["-f", v])
    subprocess.run(cmd)


@deploy.command("k8s")
@click.option("--namespace", "-n", default="default")
def deploy_k8s(namespace: str):
    """Generate Kubernetes manifests."""
    import subprocess  # nosec: B404

    cmd = ["helm", "template", "alcyoneus", "deployment/helm/alcyoneus", "-n", namespace]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        console.print(Syntax(result.stdout, "yaml"))
    else:
        console.print(f"[red]{result.stderr}[/red]")


# Debug commands
@cli.group()
def debug():
    """Debugging and inspection commands."""


@debug.command("state")
@click.argument("checkpoint_file", type=click.Path(exists=True))
def debug_state(checkpoint_file: str):
    """Inspect checkpoint state."""
    import pickle

    with open(checkpoint_file, "rb") as f:
        state = pickle.load(f)  # noqa: S301
    console.print(Syntax(json.dumps(state, default=str, indent=2), "json"))


@debug.command("trace")
@click.argument("trace_file", type=click.Path(exists=True))
def debug_trace(trace_file: str):
    """Inspect trace file."""
    with open(trace_file) as f:
        trace = json.load(f)
    console.print(Syntax(json.dumps(trace, indent=2), "json"))


@debug.command("replay")
@click.argument("graph_file", type=click.Path(exists=True))
@click.argument("checkpoint_file", type=click.Path(exists=True))
def debug_replay(graph_file: str, checkpoint_file: str):
    """Replay graph execution from checkpoint."""
    console.print("[yellow]Replay functionality[/yellow]")
    # Implementation would load checkpoint and replay


# Template functions
def _get_react_template() -> str:
    return '''"""ReAct Agent Graph Template"""

from alcyoneus.core.graph import StateGraph, Agent, ToolNode
from alcyoneus.prebuilt.tools import safe_calculator, fetch_url, web_search

def create_graph():
    graph = StateGraph()

    # Add tools
    tools = ToolNode([safe_calculator, fetch_url, web_search])
    graph.add_node("tools", tools)

    # Add agent
    agent = Agent(
        model="gpt-4o-mini",
        system_prompt="You are a helpful assistant with access to tools.",
        tool_node="tools",
    )
    graph.add_node("agent", agent)

    # Edges
    graph.set_entry_point("agent")
    graph.add_edge("agent", "tools")
    graph.add_edge("tools", "agent")

    return graph.compile()

if __name__ == "__main__":
    graph = create_graph()
    # Test
    import asyncio
    result = asyncio.run(graph.ainvoke({{"messages": ["Hello!"]}}))
    print(result)
'''


def _get_rag_template() -> str:
    return '''"""RAG Agent Graph Template"""

from alcyoneus.core.graph import StateGraph, Agent, ToolNode
from alcyoneus.prebuilt.tools import file_search, web_search, fetch_url

def create_graph():
    graph = StateGraph()

    # Tools for retrieval
    tools = ToolNode([file_search, web_search, fetch_url])
    graph.add_node("retrieve", tools)

    # Agent for generation
    agent = Agent(
        model="gpt-4o-mini",
        system_prompt="You are a RAG agent. Use retrieval tools to answer questions.",
        tool_node="retrieve",
    )
    graph.add_node("generate", agent)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "retrieve")
    graph.add_edge("retrieve", "generate")

    return graph.compile()

if __name__ == "__main__":
    graph = create_graph()
'''


def _get_swarm_template() -> str:
    return '''"""Swarm Agent Graph Template"""

from alcyoneus.core.graph import StateGraph
from alcyoneus.prebuilt.agent import SwarmAgent

def create_graph():
    graph = StateGraph()

    # Create swarm of specialized agents
    researcher = SwarmAgent(
        name="researcher",
        model="gpt-4o-mini",
        system_prompt="You research topics thoroughly.",
    )
    writer = SwarmAgent(
        name="writer",
        model="gpt-4o-mini",
        system_prompt="You write clear, engaging content.",
    )
    critic = SwarmAgent(
        name="critic",
        model="gpt-4o-mini",
        system_prompt="You critique and improve content.",
    )

    graph.add_node("researcher", researcher)
    graph.add_node("writer", writer)
    graph.add_node("critic", critic)

    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "critic")
    graph.add_edge("critic", "writer")  # Loop for refinement

    return graph.compile()

if __name__ == "__main__":
    graph = create_graph()
'''


def _get_supervisor_template() -> str:
    return '''"""Supervisor Team Graph Template"""

from alcyoneus.core.graph import StateGraph
from alcyoneus.prebuilt.agent import SupervisorTeamAgent

def create_graph():
    graph = StateGraph()

    # Supervisor with team
    team = SupervisorTeamAgent(
        name="supervisor",
        model="gpt-4o-mini",
        system_prompt="You coordinate a team of specialists.",
        team_members={
            "researcher": {"model": "gpt-4o-mini", "prompt": "Research expert"},
            "coder": {"model": "gpt-4o-mini", "prompt": "Code expert"},
            "analyst": {"model": "gpt-4o-mini", "prompt": "Data analyst"},
        }
    )

    graph.add_node("team", team)
    graph.set_entry_point("team")

    return graph.compile()

if __name__ == "__main__":
    graph = create_graph()
'''


def _get_agent_template(agent_type: str) -> str:
    templates = {
        "react": '''"""React Agent: {name}"""

from alcyoneus.prebuilt.agent import ReactAgent

agent = ReactAgent(
    model="{model}",
    system_prompt="You are a helpful assistant.",
    tools=[],  # Add tools here
)
''',
        "rag": '''"""RAG Agent: {name}"""

from alcyoneus.prebuilt.agent import RAGAgent

agent = RAGAgent(
    model="{model}",
    system_prompt="You answer questions using retrieval.",
    knowledge_base="./data",  # Path to documents
)
''',
        "swarm": '''"""Swarm Agent: {name}"""

from alcyoneus.prebuilt.agent import SwarmAgent

agent = SwarmAgent(
    model="{model}",
    system_prompt="You coordinate with other agents.",
    role="coordinator",
)
''',
    }
    return templates.get(agent_type, templates["react"])


# -----------------------------------------------------------------------------
# Version & Inspection with Machine-Readable (--json / --yaml) Outputs
# -----------------------------------------------------------------------------
@cli.command("version")
@click.option("--json", "as_json", is_flag=True, help="Output version as JSON")
@click.option("--yaml", "as_yaml", is_flag=True, help="Output version as YAML")
def cli_version(as_json: bool, as_yaml: bool) -> None:
    """Display Alcyoneus OS version information."""
    ver = _get_version()
    data = {
        "name": "alcyoneus",
        "version": ver,
        "platform": "Alcyoneus OS Multi-agent orchestration platform",
    }
    if as_json:
        click.echo(json.dumps(data, indent=2))
    elif as_yaml:
        click.echo(yaml.dump(data, sort_keys=False).strip())
    else:
        console.print(f"[bold cyan]Alcyoneus OS[/bold cyan] version [bold green]{ver}[/bold green]")


# -----------------------------------------------------------------------------
# System Health & Diagnostic Suite: alcyoneus doctor
# -----------------------------------------------------------------------------
@cli.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="Output diagnostics in JSON format")
@click.option("--yaml", "as_yaml", is_flag=True, help="Output diagnostics in YAML format")
def cli_doctor(as_json: bool, as_yaml: bool) -> None:
    """Run comprehensive system health and dependency diagnostics."""
    from alcyoneus.cli.doctor import render_diagnostics_table, run_diagnostics

    data = run_diagnostics()

    if as_json:
        click.echo(json.dumps(data, indent=2))
    elif as_yaml:
        click.echo(yaml.dump(data, sort_keys=False).strip())
    else:
        render_diagnostics_table(data, console)


# -----------------------------------------------------------------------------
# Interactive Project Scaffolding: alcyoneus init
# -----------------------------------------------------------------------------
@cli.command("init")
@click.argument("project_name", required=False)
@click.option(
    "--agent-type",
    "-a",
    type=click.Choice(["react", "plan-act-reflect", "swarm", "supervisor", "rag"]),
    help="Agent architecture pattern",
)
@click.option(
    "--storage",
    "-s",
    type=click.Choice(["memory", "sqlite", "postgres", "qdrant"]),
    help="Persistence / Checkpointer storage backend",
)
@click.option(
    "--llm-provider",
    "-p",
    type=click.Choice(["openai", "gemini", "anthropic", "ollama"]),
    help="Primary LLM provider",
)
@click.option("--output", "-o", type=click.Path(), help="Target directory for new project")
def cli_init(
    project_name: str | None,
    agent_type: str | None,
    storage: str | None,
    llm_provider: str | None,
    output: str | None,
) -> None:
    """Scaffold a new enterprise Alcyoneus OS agent project."""
    from alcyoneus.cli.scaffold import scaffold_project

    console.print("[bold cyan]🚀 Alcyoneus OS Project Scaffolding Wizard[/bold cyan]\n")

    if not project_name:
        project_name = click.prompt("Project name", default="my-alcyoneus-agent")

    if not agent_type:
        console.print("[dim]Select an agent architecture pattern:[/dim]")
        console.print("  1) react: Tool-using reasoning + acting agent")
        console.print("  2) plan-act-reflect: Autonomous planning and reflection agent")
        console.print("  3) swarm: Multi-agent cooperative handoff network")
        console.print("  4) supervisor: Multi-agent team coordinated by a supervisor")
        console.print("  5) rag: Knowledge-retrieval augmented generation agent")
        agent_choice = click.prompt(
            "Agent pattern",
            type=click.Choice(["react", "plan-act-reflect", "swarm", "supervisor", "rag"]),
            default="react",
        )
        agent_type = agent_choice

    if not storage:
        storage_choice = click.prompt(
            "Storage checkpointer",
            type=click.Choice(["memory", "sqlite", "postgres", "qdrant"]),
            default="memory",
        )
        storage = storage_choice

    if not llm_provider:
        provider_choice = click.prompt(
            "Primary LLM provider",
            type=click.Choice(["openai", "gemini", "anthropic", "ollama"]),
            default="openai",
        )
        llm_provider = provider_choice

    target_dir = Path(output) if output else Path.cwd() / project_name  # type: ignore[arg-type]

    created = scaffold_project(
        target_dir=target_dir,
        project_name=project_name,  # type: ignore[arg-type]
        agent_type=agent_type,
        storage=storage,
        llm_provider=llm_provider,
    )

    console.print(
        f"\n[bold green]✨ Project '{project_name}' successfully created in {target_dir}![/bold green]\n"
    )
    console.print("[bold]Scaffolded Files:[/bold]")
    for p in created:
        console.print(f"  • [cyan]{p.relative_to(target_dir)}[/cyan]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. cd {project_name}")
    console.print("  2. pip install -e .")
    console.print("  3. cp .env.example .env")
    console.print("  4. pytest")
    console.print("  5. python agent.py\n")


# -----------------------------------------------------------------------------
# Shell Tab Auto-Completion: alcyoneus completion
# -----------------------------------------------------------------------------
@cli.command("completion")
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh", "fish"]),
    default="bash",
    help="Target shell for tab auto-completion",
)
@click.option(
    "--install",
    is_flag=True,
    help="Automatically register completion script in shell profile",
)
def cli_completion(shell: str, install: bool) -> None:
    """Generate or install shell tab auto-completion script."""
    cmd_name = "alcyoneus"
    env_var = f"_{cmd_name.upper()}_COMPLETE"

    scripts = {
        "bash": f'eval "$({env_var}=bash_source {cmd_name})"',
        "zsh": f'eval "$({env_var}=zsh_source {cmd_name})"',
        "fish": f"eval (env {env_var}=fish_source {cmd_name})",
    }

    script_snippet = scripts.get(shell, scripts["bash"])

    if not install:
        console.print(f"# Auto-completion instructions for {shell}:")
        console.print(f"# Add the following line to your shell startup file (~/.{shell}rc):\n")
        console.print(script_snippet)
        return

    # Install flow
    home = Path.home()
    target_files = {
        "bash": home / ".bashrc",
        "zsh": home / ".zshrc",
        "fish": home / ".config" / "fish" / "completions" / f"{cmd_name}.fish",
    }

    target_path = target_files.get(shell)
    if not target_path:
        console.print(f"[red]Unsupported shell: {shell}[/red]")
        return

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        existing_content = target_path.read_text() if target_path.exists() else ""
        if script_snippet in existing_content:
            console.print(
                f"[yellow]Auto-completion snippet is already installed in {target_path}[/yellow]"
            )
            return

        with open(target_path, "a") as f:
            f.write(f"\n# Alcyoneus OS shell completion\n{script_snippet}\n")

        console.print(
            f"[bold green]Installed {shell} auto-completion to {target_path}![/bold green]"
        )
        console.print(f"To activate immediately, run: [cyan]source {target_path}[/cyan]")
    except Exception as exc:
        console.print(f"[red]Failed to install completion script: {exc}[/red]")
        console.print("You can manually append:")
        console.print(f"  {script_snippet}")


if __name__ == "__main__":
    cli()
