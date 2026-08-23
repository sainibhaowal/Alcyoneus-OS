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

## 4. Policy Engine (Access Control)

```python
from alcyoneus.core.policy import PolicyEngine, allow, deny, ask_user

engine = PolicyEngine(
    rules=[
        # Admin: full access
        allow("read").when(user_role="admin"),
        allow("write").when(user_role="admin"),
        allow("delete").when(user_role="admin"),
        
        # Editor: read/write own resources
        allow("read").when(user_role="editor").and_(resource_owner=True),
        allow("write").when(user_role="editor").and_(resource_owner=True),
        
        # Viewer: read only
        allow("read").when(user_role="viewer"),
        deny("write").when(user_role="viewer"),
        deny("delete").when(user_role="viewer"),
        
        # Default deny
        deny("all"),
    ]
)

# Check permission
allowed = engine.check(
    action="write",
    user={"role": "editor", "id": "user_123"},
    resource={"owner_id": "user_123"},
)
# Returns: True
```

### Policy DSL

```python
from alcyoneus.core.policy import (
    allow, deny, ask_user,
    when, and_, or_, not_,
    user_role, resource_owner, resource_type,
    time_between, ip_in_range,
)

rules = [
    # Time-based
    allow("write").when(
        time_between("09:00", "17:00")
    ).and_(user_role="editor"),
    
    # IP-based
    allow("admin").when(
        ip_in_range("10.0.0.0/8")
    ),
    
    # Resource-based
    allow("read").when(
        resource_type="public"
    ).or_(resource_owner=True),
    
    # Conditional
    ask_user("confirm_delete").when(
        user_role="editor"
    ).and_(action="delete"),
]

engine = PolicyEngine(rules=rules)
```

---

## 4. Policy Engine in Graph

```python
from alcyoneus.core.policy import PolicyEngine
from alcyoneus.core.graph import StateGraph

engine = PolicyEngine(rules=[...])

graph = StateGraph(MyState)
graph.add_node("process", process_node)

# Add policy check node
async def check_permission(state: MyState) -> MyState:
    allowed = engine.check(
        action="process",
        user={"role": state.user_role, "id": state.user_id},
        resource={"owner_id": state.resource_owner},
    )
    if not allowed:
        raise PermissionError("Access denied")
    return state

graph.add_node("check_perm", check_permission)
graph.add_edge(START, "check_perm")
graph.add_edge("check_perm", "process")
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