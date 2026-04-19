from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .rules import Snapshot, evaluate_signal_rule

CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class BarPoint:
    ts: datetime
    close: float
    indicators: dict[str, dict[str, Any]]


@dataclass
class Position:
    side: str
    entry_ts: datetime
    entry_price: float
    notional: float
    quantity: float
    leverage: float
    trade_no: int
    entry_fees: float
    entry_slippage: float
    entry_index: int


def _get_indicator_value(indicators: dict[str, dict[str, Any]], indicator: str, field: str) -> float | None:
    payload = indicators.get(indicator) or {}
    value = payload.get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare(operator: str, left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    return False


def _evaluate_clause(clause: dict[str, Any], snapshot: Snapshot) -> bool:
    if clause["type"] == "signal_rule":
        result = evaluate_signal_rule(clause["rule_key"], snapshot)
        return bool(result and result.triggered and (clause["side"] == "any" or result.direction == clause["side"]))

    left = _get_indicator_value(snapshot.indicators_current, clause["left"]["indicator"], clause["left"]["field"])
    right_operand = clause["right"]
    if right_operand["kind"] == "constant":
        right = float(right_operand["value"])
    else:
        right = _get_indicator_value(snapshot.indicators_current, right_operand["indicator"], right_operand["field"])
    return _compare(clause["operator"], left, right)


def _group_match(group: dict[str, Any], snapshot: Snapshot, side: str, entry_group: bool) -> bool:
    clauses = [
        clause
        for clause in group["clauses"]
        if clause["side"] == side or (not entry_group and clause["side"] == "any")
    ]
    if not clauses:
        return False
    results = [_evaluate_clause(clause, snapshot) for clause in clauses]
    if group["logic"] == "all":
        return all(results)
    return any(results)


def _unrealized_pnl(position: Position, close_price: float) -> float:
    return position.quantity * (close_price - position.entry_price)


def _close_position(
    position: Position,
    bar: BarPoint,
    costs: dict[str, float],
    cash: float,
    reason: str,
    bar_index: int,
) -> tuple[float, dict[str, Any]]:
    gross_pnl = _unrealized_pnl(position, bar.close)
    exit_fee = position.notional * (costs["fee_bps"] / 10000.0)
    exit_slippage = position.notional * (costs["slippage_bps"] / 10000.0)
    net_pnl = gross_pnl - position.entry_fees - position.entry_slippage - exit_fee - exit_slippage
    next_cash = cash + gross_pnl - exit_fee - exit_slippage
    trade = {
        "trade_no": position.trade_no,
        "side": position.side,
        "entry_ts": position.entry_ts,
        "exit_ts": bar.ts,
        "entry_price": position.entry_price,
        "exit_price": bar.close,
        "notional": position.notional,
        "quantity": position.quantity,
        "leverage": position.leverage,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "fees_paid": position.entry_fees + exit_fee,
        "slippage_paid": position.entry_slippage + exit_slippage,
        "bars_held": max(1, bar_index - position.entry_index),
        "exit_reason": reason,
        "meta": {},
    }
    return next_cash, trade


def run_backtest(
    bars: list[BarPoint],
    dsl: dict[str, Any],
    start_ts: datetime,
    initial_equity: float,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    if not bars:
        raise ValueError("missing_data")

    cash = float(initial_equity)
    peak_equity = float(initial_equity)
    position: Position | None = None
    halted = False
    halted_at: datetime | None = None
    halt_reason: str | None = None
    bankrupt = False
    points: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    max_total_drawdown = 0.0
    max_trailing_drawdown = 0.0
    trade_no = 0
    last_bar: BarPoint | None = None

    for bar_index, bar in enumerate(bars):
        if cancel_check and cancel_check():
            return {
                "status": "canceled",
                "summary": {
                    "initial_equity": initial_equity,
                    "final_equity": cash,
                    "trade_count": len(trades),
                    "halted_by_drawdown": False,
                    "halted_at": None,
                    "halt_reason": "canceled",
                    "bankrupt": False,
                    "total_return_pct": 0.0,
                    "max_total_drawdown_pct": max_total_drawdown,
                    "max_trailing_drawdown_pct": max_trailing_drawdown,
                    "win_rate": 0.0,
                    "profit_factor": None,
                    "avg_holding_bars": 0.0,
                },
                "trades": trades,
                "equity_points": points,
                "events": events,
            }

        if bar.ts < start_ts:
            last_bar = bar
            continue

        snapshot = Snapshot(
            close_current=bar.close,
            close_previous=last_bar.close if last_bar else None,
            indicators_current=bar.indicators,
            indicators_previous=last_bar.indicators if last_bar else {},
        )

        pre_action_equity = cash if position is None else cash + _unrealized_pnl(position, bar.close)
        if position is not None and _group_match(dsl["exit"], snapshot, position.side, entry_group=False):
            cash, trade = _close_position(position, bar, dsl["costs"], cash, "rule_exit", bar_index)
            position = None
            trades.append(trade)
            events.append(
                {
                    "event_ts": bar.ts,
                    "event_type": "exit_signal",
                    "severity": "info",
                    "message": "Position closed by exit rule.",
                    "payload": {"side": trade["side"], "trade_no": trade["trade_no"], "reason": trade["exit_reason"]},
                }
            )
            pre_action_equity = cash

        total_drawdown = max(0.0, (initial_equity - pre_action_equity) / initial_equity) if initial_equity > 0 else 0.0
        trailing_drawdown = max(0.0, (peak_equity - pre_action_equity) / peak_equity) if peak_equity > 0 else 0.0
        max_total_drawdown = max(max_total_drawdown, total_drawdown)
        max_trailing_drawdown = max(max_trailing_drawdown, trailing_drawdown)

        drawdown_cfg = dsl["drawdown"]
        total_breached = drawdown_cfg["max_total_drawdown_pct"] is not None and total_drawdown >= drawdown_cfg["max_total_drawdown_pct"]
        trailing_breached = drawdown_cfg["trailing_drawdown_pct"] is not None and trailing_drawdown >= drawdown_cfg["trailing_drawdown_pct"]
        if (total_breached or trailing_breached) and not halted:
            if position is not None:
                cash, trade = _close_position(position, bar, dsl["costs"], cash, "drawdown_halt", bar_index)
                position = None
                trades.append(trade)
            halted = True
            halted_at = bar.ts
            halt_reason = "drawdown"
            events.append(
                {
                    "event_ts": bar.ts,
                    "event_type": "drawdown_trigger",
                    "severity": "warn",
                    "message": "Drawdown protection triggered.",
                    "payload": {
                        "total_drawdown_pct": total_drawdown,
                        "trailing_drawdown_pct": trailing_drawdown,
                    },
                }
            )
            pre_action_equity = cash

        if pre_action_equity > peak_equity:
            peak_equity = pre_action_equity

        if not halted and position is None:
            requested_side: str | None = None
            direction_mode = dsl["sizing"]["direction_mode"]
            if direction_mode in {"long", "both"} and _group_match(dsl["entry"], snapshot, "long", entry_group=True):
                requested_side = "long"
            if direction_mode in {"short", "both"} and _group_match(dsl["entry"], snapshot, "short", entry_group=True):
                if requested_side is None:
                    requested_side = "short"

            if requested_side is not None:
                trade_no += 1
                notional = pre_action_equity * dsl["sizing"]["equity_pct"] * dsl["sizing"]["leverage"]
                if notional > 0:
                    quantity = notional / bar.close
                    if requested_side == "short":
                        quantity *= -1.0
                    entry_fee = notional * (dsl["costs"]["fee_bps"] / 10000.0)
                    entry_slippage = notional * (dsl["costs"]["slippage_bps"] / 10000.0)
                    cash -= entry_fee + entry_slippage
                    position = Position(
                        side=requested_side,
                        entry_ts=bar.ts,
                        entry_price=bar.close,
                        notional=notional,
                        quantity=quantity,
                        leverage=dsl["sizing"]["leverage"],
                        trade_no=trade_no,
                        entry_fees=entry_fee,
                        entry_slippage=entry_slippage,
                        entry_index=bar_index,
                    )
                    events.append(
                        {
                            "event_ts": bar.ts,
                            "event_type": "entry_signal",
                            "severity": "info",
                            "message": "Position opened by entry rule.",
                            "payload": {"side": requested_side, "trade_no": trade_no},
                        }
                    )

        point_equity = cash if position is None else cash + _unrealized_pnl(position, bar.close)
        point_total_drawdown = max(0.0, (initial_equity - point_equity) / initial_equity) if initial_equity > 0 else 0.0
        point_trailing_drawdown = max(0.0, (peak_equity - point_equity) / peak_equity) if peak_equity > 0 else 0.0
        max_total_drawdown = max(max_total_drawdown, point_total_drawdown)
        max_trailing_drawdown = max(max_trailing_drawdown, point_trailing_drawdown)
        if point_equity <= 0 and not halted:
            bankrupt = True
            halted = True
            halted_at = bar.ts
            halt_reason = "bankrupt"
            if position is not None:
                cash, trade = _close_position(position, bar, dsl["costs"], cash, "bankrupt_halt", bar_index)
                position = None
                trades.append(trade)
                point_equity = cash
            events.append(
                {
                    "event_ts": bar.ts,
                    "event_type": "bankrupt_halt",
                    "severity": "error",
                    "message": "Run halted because equity reached zero.",
                    "payload": {"equity": point_equity},
                }
            )

        points.append(
            {
                "ts": bar.ts,
                "close_price": bar.close,
                "equity": point_equity,
                "cash_balance": cash,
                "peak_equity": peak_equity,
                "total_drawdown_pct": point_total_drawdown,
                "trailing_drawdown_pct": point_trailing_drawdown,
                "position_side": position.side if position else None,
                "position_notional": position.notional if position else 0.0,
                "position_quantity": position.quantity if position else 0.0,
            }
        )

        last_bar = bar
        if halted:
            break

    if position is not None:
        assert last_bar is not None
        cash, trade = _close_position(position, last_bar, dsl["costs"], cash, "window_end", len(bars))
        trades.append(trade)
        position = None
        if points:
            points[-1]["equity"] = cash
            points[-1]["cash_balance"] = cash
            points[-1]["position_side"] = None
            points[-1]["position_notional"] = 0.0
            points[-1]["position_quantity"] = 0.0

    final_equity = cash
    positive = [trade["net_pnl"] for trade in trades if trade["net_pnl"] > 0]
    negative = [trade["net_pnl"] for trade in trades if trade["net_pnl"] < 0]
    wins = len(positive)
    trade_count = len(trades)
    avg_holding_bars = sum(trade["bars_held"] for trade in trades) / trade_count if trade_count > 0 else 0.0
    profit_factor = (sum(positive) / abs(sum(negative))) if negative else (None if not positive else None)
    summary = {
        "initial_equity": initial_equity,
        "final_equity": final_equity,
        "trade_count": trade_count,
        "halted_by_drawdown": halt_reason == "drawdown",
        "halted_at": halted_at.isoformat() if halted_at else None,
        "halt_reason": halt_reason,
        "bankrupt": bankrupt,
        "total_return_pct": ((final_equity - initial_equity) / initial_equity) if initial_equity > 0 else 0.0,
        "max_total_drawdown_pct": max_total_drawdown,
        "max_trailing_drawdown_pct": max_trailing_drawdown,
        "win_rate": (wins / trade_count) if trade_count > 0 else 0.0,
        "profit_factor": profit_factor,
        "avg_holding_bars": avg_holding_bars,
    }
    return {"status": "completed", "summary": summary, "trades": trades, "equity_points": points, "events": events}
