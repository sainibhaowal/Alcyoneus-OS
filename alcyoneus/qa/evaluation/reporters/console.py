"""
Console reporter for evaluation results.

Provides pretty-printed console output for evaluation reports.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO

from alcyoneus.qa.evaluation.reporters._utils import (
    case_display_name,
    format_timestamp,
    format_tool_calls,
)
from alcyoneus.qa.evaluation.reporters.base import BaseReporter


if TYPE_CHECKING:
    from alcyoneus.qa.evaluation.eval_result import EvalCaseResult, EvalReport


# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------

_ANSI = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "DIM": "\033[2m",
    "RED": "\033[31m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "BLUE": "\033[34m",
    "MAGENTA": "\033[35m",
    "CYAN": "\033[36m",
    "WHITE": "\033[37m",
    "BG_RED": "\033[41m",
    "BG_GREEN": "\033[42m",
}

_NO_COLOR = dict.fromkeys(_ANSI, "")


class Colors:
    """ANSI color code constants.

    Use ``ConsoleReporter(use_color=False)`` to disable colors per-instance
    rather than calling ``Colors.disable()``, which mutates global state and
    affects all reporter instances.
    """

    RESET = _ANSI["RESET"]
    BOLD = _ANSI["BOLD"]
    DIM = _ANSI["DIM"]
    RED = _ANSI["RED"]
    GREEN = _ANSI["GREEN"]
    YELLOW = _ANSI["YELLOW"]
    BLUE = _ANSI["BLUE"]
    MAGENTA = _ANSI["MAGENTA"]
    CYAN = _ANSI["CYAN"]
    WHITE = _ANSI["WHITE"]
    BG_RED = _ANSI["BG_RED"]
    BG_GREEN = _ANSI["BG_GREEN"]

    @classmethod
    def disable(cls) -> None:
        """Disable colors globally on the Colors class.

        .. deprecated::
            Prefer ``ConsoleReporter(use_color=False)`` which scopes the
            change to a single instance and does not affect other reporters.
        """
        for attr, _ in _ANSI.items():
            setattr(cls, attr, "")


class _C:
    """Per-instance color holder. Avoids mutating shared Colors class state."""

    __slots__ = tuple(_ANSI.keys())

    def __init__(self, use_color: bool) -> None:
        source = _ANSI if use_color else _NO_COLOR
        for k, v in source.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class ConsoleReporter(BaseReporter):
    """Pretty-print evaluation results to console.

    Provides colored, formatted output for evaluation reports
    with configurable verbosity levels.

    Attributes:
        use_color: Whether to use ANSI colors.
        verbose: Whether to show detailed output.
        output: Output stream (default: stdout).
        include_trajectory: Show trajectory and tool-call data.
        include_actual_response: Show the agent's final response text.

    Example:
        ```python
        reporter = ConsoleReporter(verbose=True)
        reporter.report(eval_report)

        # No color (e.g. for CI logs) — does NOT affect other instances
        plain = ConsoleReporter(use_color=False)
        plain.report(eval_report)
        ```
    """

    def __init__(
        self,
        use_color: bool = True,
        verbose: bool = False,
        output: TextIO | None = None,
        include_trajectory: bool = False,
        include_actual_response: bool = False,
    ):
        self.use_color = use_color
        self.verbose = verbose
        self.output = output or sys.stdout
        self.include_trajectory = include_trajectory
        self.include_actual_response = include_actual_response
        # Per-instance color strings — changing these never affects other instances
        self._c = _C(use_color)

    # --- BaseReporter interface -------------------------------------------

    def generate(self, report: EvalReport, output_dir: str | None = None) -> str | None:
        """Generate a console report (prints to output stream).

        Args:
            report: The evaluation report to display.
            output_dir: Ignored for console reporter.

        Returns:
            None (console-only reporter).
        """
        self.report(report)
        return None

    def report(self, report: EvalReport) -> None:
        """Print a complete evaluation report.

        Args:
            report: The evaluation report to display.
        """
        self._print_header(report)
        self._print_summary(report)
        self._print_criterion_stats(report)

        # Always show case details — verbose controls extra sub-fields
        self._print_case_details(report)

        self._print_footer(report)

    def _print(self, *args, **kwargs) -> None:
        try:
            print(*args, file=self.output, **kwargs)
        except UnicodeEncodeError:
            # Windows cp1252 can't render Unicode box-drawing/symbol chars;
            # fall back to an ASCII-safe representation.
            safe_args = tuple(
                a.encode(self.output.encoding or "ascii", errors="replace").decode(
                    self.output.encoding or "ascii"
                )
                if isinstance(a, str)
                else a
                for a in args
            )
            print(*safe_args, file=self.output, **kwargs)

    def _print_header(self, report: EvalReport) -> None:
        c = self._c
        title = report.eval_set_name or report.eval_set_id
        self._print()
        self._print(f"{c.BOLD}{c.CYAN}╔{'═' * 60}╗{c.RESET}")  # type: ignore[attr-defined]
        title_str = f"{c.BOLD}Evaluation Report: {title}{c.RESET}"  # type: ignore[attr-defined]
        self._print(f"{c.BOLD}{c.CYAN}║{c.RESET} {title_str}")  # type: ignore[attr-defined]
        self._print(f"{c.BOLD}{c.CYAN}╚{'═' * 60}╝{c.RESET}")  # type: ignore[attr-defined]
        self._print()

    def _print_summary(self, report: EvalReport) -> None:
        c = self._c
        summary = report.summary

        if summary.pass_rate == 1.0:
            status = f"{c.BG_GREEN}{c.WHITE}{c.BOLD} ALL PASSED {c.RESET}"  # type: ignore[attr-defined]
        elif summary.pass_rate == 0.0:
            status = f"{c.BG_RED}{c.WHITE}{c.BOLD} ALL FAILED {c.RESET}"  # type: ignore[attr-defined]
        else:
            status = f"{c.YELLOW}{c.BOLD}PARTIAL{c.RESET}"  # type: ignore[attr-defined]

        self._print(f"{c.BOLD}Summary:{c.RESET} {status}")  # type: ignore[attr-defined]
        self._print()

        total_str = f"Total Cases:  {c.BOLD}{summary.total_cases}{c.RESET}"  # type: ignore[attr-defined]
        self._print(f"  {c.DIM}├─{c.RESET} {total_str}")  # type: ignore[attr-defined]

        pass_color = c.GREEN if summary.passed_cases > 0 else c.DIM  # type: ignore[attr-defined]
        self._print(
            f"  {c.DIM}├─{c.RESET} Passed:       "  # type: ignore[attr-defined]
            f"{pass_color}{summary.passed_cases} ({summary.pass_rate:.1%}){c.RESET}"  # type: ignore[attr-defined]
        )

        fail_color = c.RED if summary.failed_cases > 0 else c.DIM  # type: ignore[attr-defined]
        self._print(
            f"  {c.DIM}├─{c.RESET} Failed:       {fail_color}{summary.failed_cases}{c.RESET}"  # type: ignore[attr-defined]
        )

        error_color = c.YELLOW if summary.error_cases > 0 else c.DIM  # type: ignore[attr-defined]
        self._print(
            f"  {c.DIM}├─{c.RESET} Errors:       {error_color}{summary.error_cases}{c.RESET}"  # type: ignore[attr-defined]
        )

        duration_str = (
            f"{summary.total_duration_seconds:.2f}s (avg: {summary.avg_duration_seconds:.2f}s)"
        )
        self._print(f"  {c.DIM}└─{c.RESET} Duration:     {duration_str}")  # type: ignore[attr-defined]
        self._print()

    def _print_criterion_stats(self, report: EvalReport) -> None:
        c = self._c
        if not report.summary.criterion_stats:
            return

        self._print(f"{c.BOLD}Criteria Results:{c.RESET}")  # type: ignore[attr-defined]
        self._print()

        HIGH_PASS_RATE = 0.9
        MED_PASS_RATE = 0.5

        for criterion, stats in report.summary.criterion_stats.items():
            pass_rate = stats.get("pass_rate", 0.0)
            avg_score = stats.get("avg_score", 0.0)
            passed = stats.get("passed", 0)
            total = stats.get("total", 0)

            if pass_rate >= HIGH_PASS_RATE:
                color, icon = c.GREEN, "✓"  # type: ignore[attr-defined]
            elif pass_rate >= MED_PASS_RATE:
                color, icon = c.YELLOW, "○"  # type: ignore[attr-defined]
            else:
                color, icon = c.RED, "✗"  # type: ignore[attr-defined]

            self._print(
                f"  {color}{icon}{c.RESET} {criterion}: "  # type: ignore[attr-defined]
                f"{passed}/{total} passed, avg score: {avg_score:.2f}"
            )

        self._print()

    def _print_case_details(self, report: EvalReport) -> None:
        c = self._c
        self._print(f"{c.BOLD}Case Details:{c.RESET}")  # type: ignore[attr-defined]
        self._print()
        for result in report.results:
            self._print_case(result)

    def _print_case(self, result: EvalCaseResult) -> None:  # noqa: PLR0912, PLR0915
        c = self._c
        if result.is_error:
            icon, color, status = "⚠", c.YELLOW, "ERROR"  # type: ignore[attr-defined]
        elif result.passed:
            icon, color, status = "✓", c.GREEN, "PASS"  # type: ignore[attr-defined]
        else:
            icon, color, status = "✗", c.RED, "FAIL"  # type: ignore[attr-defined]

        name = case_display_name(result)
        self._print(f"  {color}{icon} {status}{c.RESET} {name} ({result.duration_seconds:.2f}s)")  # type: ignore[attr-defined]

        if result.error:
            self._print(f"      {c.YELLOW}Error: {result.error}{c.RESET}")  # type: ignore[attr-defined]

        # --- Metadata (always shown when non-empty) ---
        if getattr(result, "metadata", None):
            self._print(f"      {c.BOLD}Metadata:{c.RESET}")  # type: ignore[attr-defined]
            for mk, mv in result.metadata.items():
                self._print(f"        {c.DIM}{mk}: {mv}{c.RESET}")  # type: ignore[attr-defined]

        # --- Agent response (shown when flag is set) ---
        if self.include_actual_response and result.actual_response:
            self._print(
                f"      {c.BOLD}Response:{c.RESET} {c.DIM}{result.actual_response}{c.RESET}"  # type: ignore[attr-defined]
            )

        # --- Tool calls (always shown) ---
        if result.actual_tool_calls:
            self._print(f"      {c.BOLD}Tool Calls ({len(result.actual_tool_calls)}):{c.RESET}")  # type: ignore[attr-defined]
            for tc_info in format_tool_calls(result.actual_tool_calls):
                self._print(f"        {c.CYAN}→{c.RESET} {tc_info['name']}")  # type: ignore[attr-defined]
                if tc_info.get("call_id"):
                    self._print(f"          {c.DIM}call_id: {tc_info['call_id']}{c.RESET}")  # type: ignore[attr-defined]
                if tc_info["args"] and tc_info["args"] != "{}":
                    self._print(f"          {c.DIM}args: {tc_info['args']}{c.RESET}")  # type: ignore[attr-defined]
                if tc_info["result"]:
                    self._print(f"          {c.DIM}result: {tc_info['result']}{c.RESET}")  # type: ignore[attr-defined]

        # --- Trajectory (shown when flag is set) ---
        if self.include_trajectory and result.actual_trajectory:
            self._print(
                f"      {c.BOLD}Trajectory ({len(result.actual_trajectory)} steps):{c.RESET}"  # type: ignore[attr-defined]
            )
            for step in result.actual_trajectory:
                if hasattr(step, "step_type"):
                    stype = (
                        step.step_type.value
                        if hasattr(step.step_type, "value")
                        else str(step.step_type)
                    )
                    sname = step.name if hasattr(step, "name") else str(step)
                    self._print(f"        {c.CYAN}→{c.RESET} [{stype.upper()}] {sname}")  # type: ignore[attr-defined]
                    if hasattr(step, "args") and step.args:
                        import json as _json

                        try:
                            args_str = _json.dumps(step.args, default=str, ensure_ascii=False)
                        except (TypeError, ValueError):
                            args_str = str(step.args)
                        self._print(f"          {c.DIM}args: {args_str}{c.RESET}")  # type: ignore[attr-defined]
                    if hasattr(step, "metadata") and step.metadata:
                        self._print(f"          {c.DIM}metadata: {step.metadata}{c.RESET}")  # type: ignore[attr-defined]
                    if hasattr(step, "timestamp") and step.timestamp:
                        self._print(f"          {c.DIM}timestamp: {step.timestamp}{c.RESET}")  # type: ignore[attr-defined]
                else:
                    self._print(f"        {c.CYAN}→{c.RESET} {step}")  # type: ignore[attr-defined]

        # --- Node visits (always shown) ---
        if getattr(result, "node_visits", None):
            self._print(
                f"      {c.BOLD}Node Visits:{c.RESET} "  # type: ignore[attr-defined]
                f"{c.DIM}{' → '.join(result.node_visits)}{c.RESET}"  # type: ignore[attr-defined]
            )

        # --- Node responses (always shown with full fields) ---
        if getattr(result, "node_responses", None):
            self._print(f"      {c.BOLD}Node Responses ({len(result.node_responses)}):{c.RESET}")  # type: ignore[attr-defined]
            for nr in result.node_responses:
                nr_name = (
                    nr.get("node_name", "?")
                    if isinstance(nr, dict)
                    else getattr(nr, "node_name", "?")
                )
                nr_text = (
                    nr.get("response_text", "")
                    if isinstance(nr, dict)
                    else getattr(nr, "response_text", "")
                )
                nr_tools = (
                    nr.get("tool_call_names", [])
                    if isinstance(nr, dict)
                    else getattr(nr, "tool_call_names", [])
                )
                nr_final = (
                    nr.get("is_final", False)
                    if isinstance(nr, dict)
                    else getattr(nr, "is_final", False)
                )
                nr_has_tools = (
                    nr.get("has_tool_calls", False)
                    if isinstance(nr, dict)
                    else getattr(nr, "has_tool_calls", False)
                )
                nr_timestamp = (
                    nr.get("timestamp", 0) if isinstance(nr, dict) else getattr(nr, "timestamp", 0)
                )
                nr_input_msgs = (
                    nr.get("input_messages", [])
                    if isinstance(nr, dict)
                    else getattr(nr, "input_messages", [])
                )
                marker = " [FINAL]" if nr_final else ""
                self._print(f"        {c.MAGENTA}⊙{c.RESET} {nr_name}{marker}")  # type: ignore[attr-defined]
                if nr_text:
                    self._print(f"          {c.DIM}output: {nr_text}{c.RESET}")  # type: ignore[attr-defined]
                if nr_tools:
                    self._print(f"          {c.DIM}tools: {', '.join(nr_tools)}{c.RESET}")  # type: ignore[attr-defined]
                if nr_has_tools:
                    self._print(f"          {c.DIM}has_tool_calls: True{c.RESET}")  # type: ignore[attr-defined]
                if nr_timestamp:
                    self._print(f"          {c.DIM}timestamp: {nr_timestamp}{c.RESET}")  # type: ignore[attr-defined]
                if nr_input_msgs and self.verbose:
                    self._print(f"          {c.DIM}input_messages ({len(nr_input_msgs)}):{c.RESET}")  # type: ignore[attr-defined]
                    for msg in nr_input_msgs:
                        role = msg.get("role", "?") if isinstance(msg, dict) else "?"
                        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                        self._print(f"            {c.DIM}[{role}] {content}{c.RESET}")  # type: ignore[attr-defined]

        # --- Messages (always shown) ---
        if getattr(result, "messages", None):
            self._print(f"      {c.BOLD}Messages ({len(result.messages)}):{c.RESET}")  # type: ignore[attr-defined]
            for msg in result.messages:
                role = msg.get("role", "?") if isinstance(msg, dict) else "?"
                content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                self._print(f"        {c.DIM}[{role}] {content}{c.RESET}")  # type: ignore[attr-defined]

        # --- Turn results (multi-turn per-turn data) ---
        if getattr(result, "turn_results", None):
            self._print(
                f"      {c.BOLD}Turn-by-Turn Results ({len(result.turn_results)}):{c.RESET}"  # type: ignore[attr-defined]
            )
            for tr in result.turn_results:
                tidx = tr.get("turn_index", "?")
                self._print(f"        {c.CYAN}Turn {tidx}:{c.RESET}")  # type: ignore[attr-defined]
                self._print(f"          {c.DIM}user: {tr.get('user_input', '')}{c.RESET}")  # type: ignore[attr-defined]
                self._print(f"          {c.DIM}agent: {tr.get('agent_response', '')}{c.RESET}")  # type: ignore[attr-defined]
                turn_tcs = tr.get("tool_calls", [])
                if turn_tcs:
                    self._print(f"          {c.DIM}tool_calls: {len(turn_tcs)}{c.RESET}")  # type: ignore[attr-defined]
                turn_nv = tr.get("node_visits", [])
                if turn_nv:
                    self._print(f"          {c.DIM}nodes: {' → '.join(turn_nv)}{c.RESET}")  # type: ignore[attr-defined]

        # --- Criteria results (always shown for ALL criteria with full details) ---
        for cr in result.criterion_results:
            cr_icon = "✓" if cr.passed else "✗"
            cr_color = c.GREEN if cr.passed else c.RED  # type: ignore[attr-defined]
            self._print(
                f"      {cr_color}{cr_icon}{c.RESET} {cr.criterion}: "  # type: ignore[attr-defined]
                f"{cr.score:.2f} (threshold: {cr.threshold})"
            )
            if cr.error:
                self._print(f"        {c.YELLOW}Error: {cr.error}{c.RESET}")  # type: ignore[attr-defined]
            if cr.reason:
                self._print(f"        {c.DIM}Reason: {cr.reason}{c.RESET}")  # type: ignore[attr-defined]
            # Print ALL details from the criterion (not just reason)
            if cr.details:
                for dk, dv in cr.details.items():
                    if dk == "reason":
                        continue  # Already printed above
                    self._print(f"        {c.DIM}{dk}: {dv}{c.RESET}")  # type: ignore[attr-defined]

        self._print()

    def _print_footer(self, report: EvalReport) -> None:
        c = self._c
        timestamp = format_timestamp(report.timestamp)
        self._print(f"{c.DIM}Report generated: {timestamp}{c.RESET}")  # type: ignore[attr-defined]
        self._print()


def print_report(report: EvalReport, verbose: bool = False, use_color: bool = True) -> None:
    """Convenience function to print a report to console.

    Args:
        report: The evaluation report to print.
        verbose: Whether to show detailed output.
        use_color: Whether to use ANSI colors.
    """
    ConsoleReporter(use_color=use_color, verbose=verbose).report(report)
