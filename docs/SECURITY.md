# Security — Guardrails, Policies, Guardrails

> **Protect your agents with input/output validation, tool policies, and access control.**

---

## Overview

```
Input → InputGuardrail → Agent → ToolPolicy → Tool
                              ↓
                        OutputGuardrail → Output
```

---

## 1. Input Guardrails

```python
from alcyoneus.core.guardrails import InputGuardrail

guard = InputGuardrail(
    # Block sensitive patterns
    blocked_patterns=[
        r"password\s*[:=]",
        r"api[_-]?key\s*[:=]",
        r"secret\s*[:=]",
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # credit card
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
    ],
    # Length limits
    max_length=10000,
    min_length=1,
    # Custom validator
    custom_validator=lambda text: len(text.split()) < 2000,  # max words
)

# Apply to agent
agent = Agent(
    model="...",
    input_guardrail=guard,
)
```

---

## 2. Output Guardrails

```python
from alcyoneus.core.guardrails import OutputGuardrail

guard = OutputGuardrail(
    # Require JSON schema
    require_json_schema=MyPydanticModel,
    
    # Block sensitive output
    blocked_words=[
        "internal_error",
        "stack_trace",
        "debug_info",
        "password",
        "api_key",
        "secret",
    ],
    # Custom validator
    custom_validator=lambda text: "internal" not in text.lower(),
    # Max length
    max_length=50000,
)

agent = Agent(
    model="...",
    output_guardrail=guard,
)
```

---

## 3. Tool Guardrails (Tool Policies)

```python
from alcyoneus.core.guardrails import ToolInputGuardrail, ToolOutputGuardrail

input_policy = ToolInputGuardrail(
    # Allowlist
    allowed_tools=["search", "calculate", "fetch", "memory"],
    # Blocklist
    blocked_tools=["shell", "code_exec", "sql_exec"],
    # Rate limiting
    rate_limit=100,          # calls per minute
    burst_limit=20,          # burst allowance
    # Tool-specific limits
    tool_limits={
        "fetch_url": {"rate_limit": 30, "timeout": 10},
        "code_interpreter": {"timeout": 60, "memory_mb": 256},
    },
    # Argument validation
    arg_validators={
        "shell": lambda args: "rm" not in args.get("command", ""),
        "sql": lambda args: "drop" not in args.get("query", "").lower(),
    },
)

output_policy = ToolOutputGuardrail(
    # Output validation
    blocked_patterns=[r"password", r"api_key"],
    max_length=10000,
)

agent = Agent(
    model="...",
    tool_input_guardrail=input_policy,
    tool_output_guardrail=output_policy,
)
```

---

## 4. Unified Safety & Policy Engine

Alcyoneus OS provides an enterprise-grade, declarative Policy Engine for fine-grained tool authorization, path traversal sandboxing, and Human-in-the-Loop (HITL) confirmation.

### 9-Tier Priority Evaluation Hierarchy

Policies are evaluated strictly from highest to lowest specificity:
1. **Specific Deny** (`tool="delete_database"`, `decision=DENY`)
2. **Specific Ask** (`tool="drop_table"`, `decision=ASK_USER`)
3. **Specific Allow** (`tool="safe_calculator"`, `decision=APPROVE`)
4. **Prefix Deny** (`tool="aws/*"`, `decision=DENY`)
5. **Prefix Ask** (`tool="git/*"`, `decision=ASK_USER`)
6. **Prefix Allow** (`tool="read/*"`, `decision=APPROVE`)
7. **Global Deny** (`tool="*"`, `decision=DENY`)
8. **Global Ask** (`tool="*"`, `decision=ASK_USER`)
9. **Global Allow** (`tool="*"`, `decision=APPROVE`)

### Quick Setup with Safe Defaults

```python
from alcyoneus.core.policy import PolicyEngine, safe_defaults, ask_user, deny

# safe_defaults restricts file tools to workspace_path and prompts for shell execution
engine = PolicyEngine(
    policies=[
        *safe_defaults(workspace_path="./workspace"),
        # Deny dangerous tools explicitly
        deny("eval_arbitrary_python"),
        # Ask for approval on production deployments
        ask_user("deploy_to_production"),
    ]
)
```

### ToolNode Policy Enforcement

Attach the `PolicyEngine` directly to any `ToolNode` in your `StateGraph` or `Agent`:

```python
from alcyoneus.core import ToolNode, StateGraph
from alcyoneus.core.policy import (
    PolicyEngine,
    allow,
    deny,
    ask_user,
    workspace_only,
)
from alcyoneus.prebuilt.tools import (
    file_read,
    file_write,
    shell_command,
    safe_calculator,
)

# Custom interactive confirmation handler for HITL
async def my_hitl_handler(tool_name: str, args: dict) -> bool:
    print(f"⚠️ Tool requested approval: {tool_name} with {args}")
    # In web UI / CLI: prompt user or return boolean
    return True

engine = PolicyEngine(
    policies=[
        # Sandboxing: Restrict all file reads and writes inside the workspace
        workspace_only(workspace_path="/app/sandbox", tools=["file_read", "file_write"]),
        
        # Always allow pure computational tools
        allow("safe_calculator"),
        
        # Human approval required for shell execution
        ask_user("shell_command", handler=my_hitl_handler),
        
        # Global fallback: deny everything else by default
        deny("*"),
    ]
)

# Wrap tools with the policy engine
tool_node = ToolNode(
    tools=[file_read, file_write, shell_command, safe_calculator],
    policy=engine,
)
```

### Multi-Tenant & Scoped Access

Policies can be scoped to specific tenants, user IDs, or MCP servers:

```python
from alcyoneus.core.policy import Policy, Decision

tenant_policy = Policy(
    tool="query_customer_db",
    decision=Decision.APPROVE,
    tenant_ids=("tenant_enterprise_42",),
    argument_predicate=lambda args: args.get("limit", 0) <= 100,
)

engine = PolicyEngine(policies=[tenant_policy])
```

---

## 5. Combined Guardrails

```python
agent = Agent(
    model="google/gemini-2.5-flash",
    input_guardrail=InputGuardrail(
        blocked_patterns=[r"password", r"api_key"],
        max_length=5000,
    ),
    output_guardrail=OutputGuardrail(
        blocked_words=["internal", "secret"],
        require_json_schema=MyOutputSchema,
    ),
    tool_input_guardrail=ToolInputGuardrail(
        allowed_tools=["search", "calc"],
        blocked_tools=["shell"],
        rate_limit=50,
    ),
    tool_output_guardrail=ToolOutputGuardrail(
        blocked_words=["secret", "internal"],
        max_length=5000,
    ),
)
```

---

## 5. Custom Validators

```python
from alcyoneus.core.guardrails import InputGuardrail

class CustomValidator:
    def __init__(self, forbidden_domains):
        self.forbidden = forbidden_domains
    
    def __call__(self, text: str) -> bool:
        for domain in self.forbidden:
            if domain in text:
                return False
        return True

guard = InputGuardrail(
    custom_validator=CustomValidator(["evil.com", "malware.site"]),
)
```

---

## 6. Guardrail Events

```python
# Guardrail events are logged automatically via callbacks
from alcyoneus.utils.callbacks import CallbackManager

def on_guardrail_violation(event_data):
    print(f"Violation: {event_data['guardrail_type']} - {event_data['matched_pattern']}")

guard = InputGuardrail(
    blocked_patterns=["password"],
    on_violation=on_violation,  # Not directly supported; use callbacks instead
)

# Use CallbackManager for violation events
callbacks = CallbackManager([
    LoggingCallback(),
    # Custom callback for violations
])
```

**Note:** Direct `on_violation` callbacks on guardrails are not currently supported. Use `CallbackManager` with custom callbacks to capture guardrail violations.
```

---

## 6. Best Practices

| Practice | Why |
|----------|-----|
| Layer defenses | Multiple layers catch different threats |
| Start strict, relax | Safer to add permissions than remove |
| Log violations | Audit trail for security |
| Test guardrails | Unit test each rule |
| Monitor false positives | Adjust patterns as needed |
| Separate environments | Different policies per env |