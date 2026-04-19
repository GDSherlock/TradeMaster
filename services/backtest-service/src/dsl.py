from __future__ import annotations

from copy import deepcopy
from typing import Any

from .catalog import CLAUSE_SIDES, DEFAULT_DSL, INDICATOR_FIELDS, OPERATORS, SIGNAL_RULES, SIDES

ALLOWED_LOGIC = {"all", "any"}
ALLOWED_CLAUSE_TYPES = {"signal_rule", "indicator_compare"}
ALLOWED_ACTIONS = {"flatten_and_halt"}
ALLOWED_FILL_POLICIES = {"current_bar_close"}


class DslValidationError(ValueError):
    pass


def _as_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DslValidationError(f"{path} must be an object")
    return value


def _as_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise DslValidationError(f"{path} must be an array")
    return value


def _as_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise DslValidationError(f"{path} must be a string")
    normalized = value.strip()
    if not normalized:
        raise DslValidationError(f"{path} must not be empty")
    return normalized


def _as_float(value: Any, path: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DslValidationError(f"{path} must be numeric") from None
    return number


def _normalize_indicator_ref(value: Any, path: str) -> dict[str, str]:
    payload = _as_mapping(value, path)
    indicator = _as_string(payload.get("indicator"), f"{path}.indicator").lower()
    field = _as_string(payload.get("field"), f"{path}.field")
    allowed_fields = INDICATOR_FIELDS.get(indicator)
    if not allowed_fields:
        raise DslValidationError(f"{path}.indicator is not supported")
    if field not in allowed_fields:
        raise DslValidationError(f"{path}.field is not supported for {indicator}")
    return {"indicator": indicator, "field": field}


def _normalize_operand(value: Any, path: str) -> dict[str, Any]:
    payload = _as_mapping(value, path)
    kind = _as_string(payload.get("kind"), f"{path}.kind").lower()
    if kind == "constant":
        return {"kind": kind, "value": _as_float(payload.get("value"), f"{path}.value")}
    if kind == "field":
        ref = _normalize_indicator_ref(payload, path)
        ref["kind"] = kind
        return ref
    raise DslValidationError(f"{path}.kind must be one of constant/field")


def _normalize_clause(clause: Any, path: str, allow_any_side: bool) -> dict[str, Any]:
    payload = _as_mapping(clause, path)
    clause_type = _as_string(payload.get("type"), f"{path}.type").lower()
    if clause_type not in ALLOWED_CLAUSE_TYPES:
        raise DslValidationError(f"{path}.type is not supported")

    side = _as_string(payload.get("side"), f"{path}.side").lower()
    allowed_sides = set(CLAUSE_SIDES if allow_any_side else ("long", "short"))
    if side not in allowed_sides:
        raise DslValidationError(f"{path}.side is not supported")

    if clause_type == "signal_rule":
        rule_key = _as_string(payload.get("rule_key"), f"{path}.rule_key").upper()
        if rule_key not in SIGNAL_RULES:
            raise DslValidationError(f"{path}.rule_key is not supported")
        return {"type": clause_type, "side": side, "rule_key": rule_key}

    operator = _as_string(payload.get("operator"), f"{path}.operator")
    if operator not in OPERATORS:
        raise DslValidationError(f"{path}.operator is not supported")
    return {
        "type": clause_type,
        "side": side,
        "left": _normalize_indicator_ref(payload.get("left"), f"{path}.left"),
        "operator": operator,
        "right": _normalize_operand(payload.get("right"), f"{path}.right"),
    }


def _normalize_group(value: Any, path: str, allow_any_side: bool) -> dict[str, Any]:
    payload = _as_mapping(value, path)
    logic = _as_string(payload.get("logic"), f"{path}.logic").lower()
    if logic not in ALLOWED_LOGIC:
        raise DslValidationError(f"{path}.logic must be all or any")
    clauses = [_normalize_clause(item, f"{path}.clauses[{index}]", allow_any_side) for index, item in enumerate(_as_list(payload.get("clauses", []), f"{path}.clauses"))]
    return {"logic": logic, "clauses": clauses}


def normalize_dsl(dsl: Any) -> dict[str, Any]:
    payload = deepcopy(DEFAULT_DSL)
    source = _as_mapping(dsl, "dsl")

    payload["entry"] = _normalize_group(source.get("entry", payload["entry"]), "dsl.entry", allow_any_side=False)
    if not payload["entry"]["clauses"]:
        raise DslValidationError("dsl.entry.clauses must contain at least one clause")

    payload["exit"] = _normalize_group(source.get("exit", payload["exit"]), "dsl.exit", allow_any_side=True)

    sizing = _as_mapping(source.get("sizing", payload["sizing"]), "dsl.sizing")
    equity_pct = _as_float(sizing.get("equity_pct"), "dsl.sizing.equity_pct")
    leverage = _as_float(sizing.get("leverage"), "dsl.sizing.leverage")
    direction_mode = _as_string(sizing.get("direction_mode"), "dsl.sizing.direction_mode").lower()
    if not 0 < equity_pct <= 1:
        raise DslValidationError("dsl.sizing.equity_pct must be within (0, 1]")
    if not 0 < leverage <= 50:
        raise DslValidationError("dsl.sizing.leverage must be within (0, 50]")
    if direction_mode not in SIDES:
        raise DslValidationError("dsl.sizing.direction_mode is not supported")
    payload["sizing"] = {
        "equity_pct": equity_pct,
        "leverage": leverage,
        "direction_mode": direction_mode,
    }

    costs = _as_mapping(source.get("costs", payload["costs"]), "dsl.costs")
    fee_bps = _as_float(costs.get("fee_bps"), "dsl.costs.fee_bps")
    slippage_bps = _as_float(costs.get("slippage_bps"), "dsl.costs.slippage_bps")
    if fee_bps < 0 or slippage_bps < 0:
        raise DslValidationError("dsl.costs.* must be >= 0")
    payload["costs"] = {"fee_bps": fee_bps, "slippage_bps": slippage_bps}

    drawdown = _as_mapping(source.get("drawdown", payload["drawdown"]), "dsl.drawdown")
    action = _as_string(drawdown.get("action"), "dsl.drawdown.action").lower()
    if action not in ALLOWED_ACTIONS:
        raise DslValidationError("dsl.drawdown.action is not supported")
    max_total = drawdown.get("max_total_drawdown_pct")
    trailing = drawdown.get("trailing_drawdown_pct")
    max_total_value = _as_float(max_total, "dsl.drawdown.max_total_drawdown_pct") if max_total is not None else None
    trailing_value = _as_float(trailing, "dsl.drawdown.trailing_drawdown_pct") if trailing is not None else None
    if max_total_value is None and trailing_value is None:
        raise DslValidationError("dsl.drawdown requires at least one threshold")
    for label, number in (
        ("dsl.drawdown.max_total_drawdown_pct", max_total_value),
        ("dsl.drawdown.trailing_drawdown_pct", trailing_value),
    ):
        if number is None:
            continue
        if not 0 < number <= 1:
            raise DslValidationError(f"{label} must be within (0, 1]")
    payload["drawdown"] = {
        "max_total_drawdown_pct": max_total_value,
        "trailing_drawdown_pct": trailing_value,
        "action": action,
    }

    execution = _as_mapping(source.get("execution", payload["execution"]), "dsl.execution")
    fill_policy = _as_string(execution.get("fill_policy"), "dsl.execution.fill_policy").lower()
    if fill_policy not in ALLOWED_FILL_POLICIES:
        raise DslValidationError("dsl.execution.fill_policy is not supported")
    payload["execution"] = {"fill_policy": fill_policy}

    entry_clause_sides = {clause["side"] for clause in payload["entry"]["clauses"]}
    if direction_mode == "long" and "short" in entry_clause_sides:
        raise DslValidationError("dsl.entry short clauses are not allowed when direction_mode=long")
    if direction_mode == "short" and "long" in entry_clause_sides:
        raise DslValidationError("dsl.entry long clauses are not allowed when direction_mode=short")

    return payload
