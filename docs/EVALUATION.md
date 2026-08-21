# Evaluation — CI/CD Quality Gates

> **Automated quality assurance for your agents.**

---

## Overview

```
EvalSet (test cases) → AgentEvaluator → Report (pass/fail, scores)
```

---

## 1. Define Test Cases

```python
from alcyoneus.qa.evaluation import EvalCase, EvalSet

eval_set = EvalSet(cases=[
    # Happy path
    EvalCase(
        name="order_happy_path",
        input={
            "user_id": "user_123",
            "items": [{"sku": "ABC", "qty": 1, "price": 29.99}]
        },
        expected_output={
            "confirmed": True,
            "payment_intent_id": "pay_*"
        },
        criteria=["factual_accuracy", "trajectory_match"],
    ),
    
    # Edge case
    EvalCase(
        name="payment_failure",
        input={
            "user_id": "user_456",
            "items": [],
            "force_fail": True
        },
        expected_output={
            "error": "payment_failed"
        },
        criteria=["safety"],
    ),
    
    # Multi-turn
    EvalCase(
        name="multi_turn_conversation",
        input={"user_id": "user_789"},
        expected_trajectory=[
            {"node": "greet"},
            {"node": "collect_info"},
            {"node": "confirm"},
        ],
        criteria=["trajectory_match"],
    ),
]
```

---

## 2. Configure Criteria

```python
from alcyoneus.qa.evaluation import (
    EvalConfig,
    FactualAccuracyCriterion,
    HallucinationCriterion,
    TrajectoryMatchCriterion,
    RubricCriterion,
    SafetyCriterion,
    SimulationGoalsCriterion,
)

config = EvalConfig(
    criteria=[
        # Factual accuracy (LLM judge)
        FactualAccuracyCriterion(
            threshold=0.8,
            judge_model="gpt-4o",
        ),
        
        # Hallucination detection
        HallucinationCriterion(
            threshold=0.1,
            judge_model="gpt-4o",
        ),
        
        # Trajectory matching
        TrajectoryMatchCriterion(
            expected_steps=["calculate", "charge", "fulfill"],
            exact_order=True,
        ),
        
        # Safety
        SafetyCriterion(
            blocked_patterns=["password", "secret", "api_key", "ssn"],
            threshold=0.0,
        ),
        
        # Rubric (custom criteria)
        RubricCriterion(
            rubric={
                "politeness": "Response should be polite and helpful",
                "completeness": "All user questions addressed",
            },
            judge_model="gpt-4o",
        ),
        
        # Simulation goals
        SimulationGoalsCriterion(
            goals=["complete_order", "send_confirmation"],
            judge_model="gpt-4o",
        ),
    ],
    
    # Reporters
    reporters=[
        ConsoleReporter(),
        JSONReporter("eval_results.json"),
        HTMLReporter("eval_report.html"),
        JUnitReporter("eval_junit.xml"),  # for CI
    ],
    
    # Run each case N times
    num_runs=3,
    
    # Parallel execution
    max_concurrent=5,
)
```

---

## 3. Run Evaluation

```python
from alcyoneus.qa.evaluation import AgentEvaluator

evaluator = AgentEvaluator(compiled, config)

# Run full evaluation
report = await evaluator.evaluate(eval_set)

print(f"Total: {report.total}")
print(f"Passed: {report.passed}")
print(f"Failed: {report.failed}")
print(f"Avg Score: {report.avg_score:.2f}")

# Detailed results
for case_result in report.results:
    print(f"\nCase: {case_result.case_name}")
    print(f"  Passed: {case_result.passed}")
    print(f"  Score: {case_result.score:.2f}")
    for criterion_result in case_result.criterion_results:
        print(f"    {criterion_result.name}: {criterion_result.score:.2f} ({criterion_result.passed})")

# CI integration
if not report.all_passed:
    exit(1)  # Fail CI
```

---

## 4. Reporters

```python
from alcyoneus.qa.evaluation import (
    ConsoleReporter, JSONReporter, HTMLReporter, JUnitReporter
)

config = EvalConfig(
    reporters=[
        ConsoleReporter(),                    # Terminal output
        JSONReporter("eval_results.json"),    # Machine readable
        HTMLReporter("eval_report.html"),     # Visual report
        JUnitReporter("eval_junit.xml"),      # CI integration
    ],
)
```

---

## 5. Simulators (User Behavior)

```python
from alcyoneus.qa.evaluation import UserSimulator, SimulationConfig

simulator = UserSimulator(
    config=SimulationConfig(
        persona="impatient_customer",
        max_turns=5,
        error_injection_rate=0.1,  # 10% errors
        latency_ms=100,            # Simulated latency
    )
)

# Run batch simulation
results = await simulator.run_batch(compiled, num_sessions=100)

# Analyze
print(f"Success rate: {results.success_rate:.2%}")
print(f"Avg turns: {results.avg_turns:.1f}")
print(f"Errors encountered: {results.error_rate:.2%}")
```

### Built-in Personas

| Persona | Behavior |
|---------|----------|
| `impatient_customer` | Short responses, repeats requests |
| `confused_customer` | Asks clarifying questions |
| `expert_customer` | Uses technical terms |
| `adversarial` | Tries to break guardrails |

---

## 5. Custom Criteria

```python
from alcyoneus.qa.evaluation import Criterion, CriterionResult

class CustomCriterion(Criterion):
    name = "custom_check"
    
    async def evaluate(self, case: EvalCase, result: EvalResult) -> CriterionResult:
        # Custom logic
        score = 1.0 if "required_field" in result.state else 0.0
        return CriterionResult(
            name=self.name,
            score=score,
            passed=score > 0.5,
            details={"missing": "required_field" not in result.state}
        )

config = EvalConfig(criteria=[CustomCriterion()])
```

---

## 5. CI Integration

```yaml
# .github/workflows/eval.yml
name: Evaluation
on: [push, pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[eval]"
      - run: pytest tests/ -q
      - run: python -m myapp.eval.run  # runs AgentEvaluator
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
```

---

## 6. Evaluation Dataset (YAML)

```yaml
# eval_cases.yaml
cases:
  - name: order_happy_path
    input:
      user_id: "user_123"
      items:
        - sku: "ABC"
          qty: 1
          price: 29.99
    expected_output:
      confirmed: true
      payment_intent_id: "pay_*"
    criteria:
      - factual_accuracy
      - trajectory_match

  - name: payment_failure
    input:
      user_id: "user_456"
      items: []
      force_fail: true
    expected_output:
      error: "payment_failed"
    criteria:
      - safety
```

```python
from alcyoneus.qa.evaluation import load_eval_set

eval_set = load_eval_set("eval_cases.yaml")
```

---

## 7. Interpreting Results

| Metric | Target |
|--------|--------|
| Overall pass rate | > 95% |
| Avg factual accuracy | > 0.85 |
| Hallucination rate | < 0.05 |
| Safety violations | 0 |
| Trajectory match | > 0.9 |

---

## 7. Debugging Failures

```python
# Get detailed failure info
for case_result in report.results:
    if not case_result.passed:
        print(f"FAILED: {case_result.case_name}")
        for cr in case_result.criterion_results:
            if not cr.passed:
                print(f"  {cr.name}: {cr.score:.2f} - {cr.details}")
```