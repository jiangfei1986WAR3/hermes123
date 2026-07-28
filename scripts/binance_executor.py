#!/usr/bin/env python3
"""
binance_executor.py - 币安合约执行引擎
读取交易计划 JSON → 设杠杆 → 设逐仓 → 开仓 → 挂止损止盈 → 管理持仓
纯公开 API + 签名请求，不依赖第三方库（只用 requests）
"""

import json
import hmac
import hashlib
import time
import math
import sys
import os
import logging
from urllib.parse import urlencode
from datetime import datetime, timezone

import requests

# ─── 配置 ─────────────────────────────────────────────
CONFIG_PATH = os.path.expanduser("~/.hermes/trading-config.json")
PLANS_DIR   = os.path.expanduser("~/.hermes/trading-plans")
EVENTS_DIR  = os.path.expanduser("~/.hermes/trading-events")
HISTORY_DIR = os.path.expanduser("~/.hermes/trading-history")
STATE_FILE  = os.path.expanduser("~/.hermes/trading-state.json")
LOG_PATH    = os.path.expanduser("~/.hermes/trading-executor.log")

BASE_URL    = "https://fapi.binance.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("executor")


# ─── 加载配置 ──────────────────────────────────────────
def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


CFG = load_config()
API_KEY    = CFG["api_key"]
API_SECRET = CFG["api_secret"]
IS_TESTNET = CFG.get("testnet", False)

if IS_TESTNET:
    BASE_URL = "https://testnet.binancefuture.com"
    log.info("运行模式: 测试网 (testnet)")
else:
    log.info("运行模式: 实盘 (mainnet)")


# ─── 签名请求 ──────────────────────────────────────────
def _sign(params: dict) -> dict:
    params["timestamp"] = int(time.time() * 1000)
    query = urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = sig
    return params


def _headers() -> dict:
    return {"X-MBX-APIKEY": API_KEY}


def api_get(path: str, params: dict = None, signed: bool = False) -> dict:
    params = params or {}
    if signed:
        params = _sign(params)
    r = requests.get(f"{BASE_URL}{path}", params=params, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def api_post(path: str, params: dict = None, signed: bool = True) -> dict:
    params = params or {}
    if signed:
        params = _sign(params)
    r = requests.post(f"{BASE_URL}{path}", params=params, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def api_delete(path: str, params: dict = None, signed: bool = True) -> dict:
    params = params or {}
    if signed:
        params = _sign(params)
    r = requests.delete(f"{BASE_URL}{path}", params=params, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


# ─── 交易对精度 ────────────────────────────────────────
_symbol_info_cache: dict = {}

def get_symbol_info(symbol: str) -> dict:
    """获取交易对的精度、最小数量、stepSize 等信息"""
    if symbol in _symbol_info_cache:
        return _symbol_info_cache[symbol]
    data = api_get("/fapi/v1/exchangeInfo")
    for s in data.get("symbols", []):
        if s["symbol"] == symbol:
            info = {
                "price_precision": s.get("pricePrecision", 2),
                "quantity_precision": s.get("quantityPrecision", 3),
                "filters": {f["filterType"]: f for f in s.get("filters", [])},
            }
            _symbol_info_cache[symbol] = info
            return info
    raise ValueError(f"找不到交易对: {symbol}")


def round_price(symbol: str, price: float) -> float:
    info = get_symbol_info(symbol)
    tick = info["filters"].get("PRICE_FILTER", {})
    tick_str = tick.get("tickSize", "0")
    tick_size = float(tick_str)
    if tick_size > 0:
        # 用原始字符串解析精度，避免 float → str 产生科学计数法（如 1e-05）
        if "." in tick_str:
            decimals = len(tick_str.rstrip("0").split(".")[-1])
        else:
            decimals = 0
        return round(round(price / tick_size) * tick_size, decimals)
    return round(price, info["price_precision"])


def round_qty(symbol: str, qty: float) -> float:
    info = get_symbol_info(symbol)
    lot = info["filters"].get("LOT_SIZE", {})
    step_str = lot.get("stepSize", "0")
    step = float(step_str)
    if step > 0:
        # 用原始字符串解析精度，避免 float → str 产生科学计数法（如 1e-05）
        if "." in step_str:
            decimals = len(step_str.rstrip("0").split(".")[-1])
        else:
            decimals = 0
        result = math.floor(qty / step + 1e-9) * step
        # 整数精度币种（如 ENA stepSize=1）必须返回 int，否则 Binance 拒 400
        if decimals == 0:
            return int(round(result))
        return round(result, decimals)
    return math.floor(qty * (10 ** info["quantity_precision"])) / (10 ** info["quantity_precision"])


def min_notional(symbol: str) -> float:
    info = get_symbol_info(symbol)
    mn = info["filters"].get("MIN_NOTIONAL", {})
    return float(mn.get("notional", mn.get("minNotional", 5)))


# ─── 账户查询 ──────────────────────────────────────────
def get_balance() -> dict:
    data = api_get("/fapi/v2/balance", signed=True)
    result = {}
    for item in data:
        result[item["asset"]] = {
            "balance": float(item.get("balance", 0)),
            "available": float(item.get("availableBalance", 0)),
        }
    return result


def get_positions() -> list:
    data = api_get("/fapi/v2/positionRisk", signed=True)
    positions = []
    for p in data:
        amt = float(p.get("positionAmt", 0))
        if amt != 0:
            positions.append({
                "symbol": p["symbol"],
                "amount": amt,
                "entry_price": float(p.get("entryPrice", 0)),
                "mark_price": float(p.get("markPrice", 0)),
                "unrealized_pnl": float(p.get("unRealizedProfit", 0)),
                "leverage": int(float(p.get("leverage", 1))),
                "margin_type": p.get("marginType", ""),
                "liquidation_price": float(p.get("liquidationPrice", 0)),
            })
    return positions


def get_open_orders(symbol: str = None) -> list:
    params = {}
    if symbol:
        params["symbol"] = symbol
    return api_get("/fapi/v1/openOrders", params=params, signed=True)


# ─── 执行操作 ──────────────────────────────────────────
def set_leverage(symbol: str, leverage: int) -> dict:
    try:
        return api_post("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})
    except requests.exceptions.HTTPError as e:
        # 如果杠杆没变化，币安会返回 400，但这不是错误
        if "No need to change leverage" in str(e.response.text):
            log.info(f"{symbol} 杠杆已是 {leverage}x，无需修改")
            return {"leverage": leverage, "symbol": symbol}
        raise


def set_margin_type(symbol: str, margin_type: str = "ISOLATED") -> dict:
    try:
        return api_post("/fapi/v1/marginType", {"symbol": symbol, "marginType": margin_type})
    except requests.exceptions.HTTPError as e:
        if "No need to change margin type" in str(e.response.text):
            log.info(f"{symbol} 已是逐仓模式，无需修改")
            return {"marginType": margin_type, "symbol": symbol}
        raise


def place_order(symbol: str, side: str, order_type: str, quantity: float = None,
                price: float = None, stop_price: float = None,
                close_position: bool = False, reduce_only: bool = False,
                time_in_force: str = None, working_type: str = "MARK_PRICE",
                position_side: str = None) -> dict:
    params = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
    }
    if position_side:
        params["positionSide"] = position_side
    if quantity is not None:
        params["quantity"] = quantity
    if price is not None:
        params["price"] = price
    if stop_price is not None:
        params["stopPrice"] = stop_price
    if close_position:
        params["closePosition"] = "true"
    if reduce_only:
        params["reduceOnly"] = "true"
    if time_in_force:
        params["timeInForce"] = time_in_force
    if working_type and order_type in ("STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
        params["workingType"] = working_type
    return api_post("/fapi/v1/order", params)


def _place_conditional_order(symbol: str, side: str, order_type: str,
                             stop_price: float, quantity: float = None,
                             position_side: str = None,
                             working_type: str = "MARK_PRICE") -> dict:
    """
    挂条件单（STOP_MARKET / TAKE_PROFIT_MARKET）via Algo Order API。

    2025-11 起币安将条件单从 /fapi/v1/order 迁移到 /fapi/v1/algoOrder，
    旧端点返回 -4120 (STOP_ORDER_SWITCH_ALGO)。

    参数映射（旧 → 新）：
      stopPrice   → triggerPrice
      新增 algoType = "CONDITIONAL"
      positionSide 必传（LONG / SHORT，双向持仓模式）

    返回 algoId（非 orderId）。
    """
    if not position_side:
        # 安全默认：平仓方向推断持仓方向
        position_side = "LONG" if side == "SELL" else "SHORT"

    params = {
        "symbol": symbol,
        "side": side,
        "positionSide": position_side,
        "type": order_type,
        "algoType": "CONDITIONAL",
        "triggerPrice": stop_price,
        "workingType": working_type,
    }
    if quantity is not None:
        params["quantity"] = quantity

    return api_post("/fapi/v1/algoOrder", params)


def get_open_algo_orders(symbol: str = None) -> list:
    """查询 Algo 条件单（止损/止盈），2025-11 后条件单走独立系统"""
    params = {}
    if symbol:
        params["symbol"] = symbol
    return api_get("/fapi/v1/openAlgoOrders", params=params, signed=True)


def cancel_all_orders(symbol: str, force: bool = False) -> list:
    """撤销所有挂单（普通单 + Algo 条件单）。
    有持仓时默认拒绝执行，force=True 强制撤销。"""
    if not force:
        try:
            positions = get_positions()
            if any(p["symbol"] == symbol for p in positions):
                log.warning(f"⚠️ {symbol} 有活跃持仓，拒绝撤单（force=True 可强制执行）")
                return []
        except Exception as e:
            log.warning(f"⚠️ 查询持仓失败，保守拒绝撤单: {symbol} ({e})")
            return []
    results = []
    # 撤普通单
    orders = get_open_orders(symbol)
    for o in orders:
        try:
            r = api_delete("/fapi/v1/order", {"symbol": symbol, "orderId": o["orderId"]})
            results.append(r)
        except Exception as e:
            log.warning(f"撤单失败 {symbol} orderId={o.get('orderId')}: {e}")
    # 撤 Algo 条件单
    try:
        algo_orders = get_open_algo_orders(symbol)
        for o in algo_orders:
            try:
                r = api_delete("/fapi/v1/algoOrder", {"symbol": symbol, "algoId": str(o["algoId"])})
                results.append(r)
            except Exception as e:
                log.warning(f"撤 Algo 单失败 {symbol} algoId={o.get('algoId')}: {e}")
    except Exception as e:
        log.warning(f"查询 Algo 挂单失败 {symbol}: {e}")
    return results


# ─── 核心：执行交易计划 ────────────────────────────────
def execute_plan(plan_path: str) -> dict:
    """
    读取计划 JSON 文件，执行完整的开仓流程：
    1. 检查是否有其他持仓（最多N个，由config的max_positions控制）
    2. 设置杠杆和逐仓模式
    3. 市价开仓
    4. 挂止损单
    5. 挂止盈单（分批）
    返回执行结果
    """
    with open(plan_path) as f:
        plan = json.load(f)

    symbol    = plan["symbol"]
    direction = plan["direction"]
    result = {"symbol": symbol, "direction": direction, "steps": [], "success": False}

    log.info(f"═══ 开始执行计划: {symbol} {direction.upper()} ═══")

    # 0. 检查已有持仓
    positions = get_positions()
    existing = [p for p in positions if p["symbol"] != symbol]
    same_pos = [p for p in positions if p["symbol"] == symbol]

    if len(existing) >= CFG.get("max_positions", 1):
        msg = f"已有持仓 {existing[0]['symbol']}，最多持 {CFG.get('max_positions', 1)} 个，跳过"
        log.warning(msg)
        result["steps"].append({"step": "check_position", "status": "BLOCKED", "msg": msg})
        return result

    if same_pos:
        msg = f"{symbol} 已有持仓，不重复开仓"
        log.warning(msg)
        result["steps"].append({"step": "check_position", "status": "SKIP", "msg": msg})
        return result

    result["steps"].append({"step": "check_position", "status": "OK", "msg": "无冲突持仓"})

    # 1. 计算参数
    is_btc = symbol == "BTCUSDT"
    margin   = CFG.get("btc_margin", 10) if is_btc else CFG.get("default_margin", 10)
    leverage = CFG.get("btc_leverage", 20) if is_btc else CFG.get("default_leverage", 10)

    entry_price = plan.get("entry_trigger") or plan["entry"]["trigger_price"]
    stop_loss   = plan.get("stop_loss") or plan["stop_loss"]
    take_profits = plan.get("take_profits", [])

    quantity = round_qty(symbol, (margin * leverage) / entry_price)

    if quantity <= 0:
        msg = f"计算数量为 0，保证金 {margin}U × {leverage}x / 入场价 {entry_price} 不足"
        log.error(msg)
        result["steps"].append({"step": "calc_qty", "status": "ERROR", "msg": msg})
        return result

    log.info(f"参数: 保证金={margin}U 杠杆={leverage}x 数量={quantity} 入场≈{entry_price}")
    result["steps"].append({"step": "calc_params", "status": "OK",
                            "margin": margin, "leverage": leverage, "quantity": quantity})

    # ═══ 防错校验层（下单前最后一道关卡）═══
    errors = []

    # 校验1: 方向合理性（多单入场价必须 > 止损价，空单反之）
    if direction == "long" and entry_price <= stop_loss:
        errors.append(f"多单入场价 {entry_price} ≤ 止损价 {stop_loss}，方向数据矛盾")
    if direction == "short" and entry_price >= stop_loss:
        errors.append(f"空单入场价 {entry_price} ≥ 止损价 {stop_loss}，方向数据矛盾")

    # 校验2: 当前市场价与入场价偏差不能过大（>10% 说明数据可能串了）
    try:
        ticker = api_get("/fapi/v1/ticker/price", {"symbol": symbol}, signed=True)
        current_price = float(ticker["price"])
        deviation = abs(current_price - entry_price) / current_price * 100
        if deviation > 10:
            errors.append(
                f"入场价 {entry_price} 与当前价 {current_price:.4f} 偏差 {deviation:.1f}%，"
                f"疑似数据错误（同交易对？请确认）")
    except Exception as e:
        log.warning(f"获取当前价失败，跳过偏差校验: {e}")

    # 校验3: 名义价值合理性（margin×leverage 应约等于 qty×entry）
    expected_notional = margin * leverage
    actual_notional = quantity * entry_price
    if actual_notional > 0 and abs(actual_notional - expected_notional) / expected_notional > 0.15:
        errors.append(
            f"名义价值偏差过大: 期望≈{expected_notional}U 实际={actual_notional:.1f}U，"
            f"数量或价格可能有误")

    # 校验4: 止盈方向（多单TP必须高于入场价，空单TP必须低于）
    for i, tp in enumerate(take_profits):
        tp_price = tp["price"]
        if direction == "long" and tp_price <= entry_price:
            errors.append(f"TP{i+1} 价格 {tp_price} ≤ 入场价 {entry_price}，多单止盈方向错误")
        if direction == "short" and tp_price >= entry_price:
            errors.append(f"TP{i+1} 价格 {tp_price} ≥ 入场价 {entry_price}，空单止盈方向错误")

    # 校验5: 止损距离不能太离谱（>20% 说明止损价可能写错了）
    sl_distance_pct = abs(entry_price - stop_loss) / entry_price * 100
    if sl_distance_pct > 20:
        errors.append(f"止损距离 {sl_distance_pct:.1f}% 异常大（正常应 <5%），数据可能有误")

    if errors:
        for err in errors:
            log.error(f"🚫 校验失败: {err}")
        result["steps"].append({"step": "safety_check", "status": "REJECTED", "errors": errors})
        result["success"] = False
        return result

    log.info("✅ 防错校验全部通过")
    result["steps"].append({"step": "safety_check", "status": "PASSED"})
    # ═══ 校验层结束 ═══

    # ═══ 校验6: 入场偏差门（价格偏离触发价超过止损距离则放弃）═══
    try:
        _stop_dist = abs(entry_price - stop_loss)
        _price_dev = abs(current_price - entry_price)
        if _price_dev > _stop_dist:
            msg = (f"入场偏差过大: 当前价 {current_price:.6g} 偏离触发价 {entry_price:.6g} "
                   f"达 {_price_dev:.6g}，超过止损距离 {_stop_dist:.6g}，放弃入场")
            log.warning(f"🚫 {msg}")
            result["steps"].append({"step": "deviation_check", "status": "REJECTED", "msg": msg})
            result["success"] = False
            return result
        log.info(f"✅ 入场偏差检查通过: 偏差 {_price_dev:.6g} ≤ 止损距离 {_stop_dist:.6g}")
        result["steps"].append({"step": "deviation_check", "status": "PASSED"})
    except NameError:
        # current_price 未定义（校验2获取价格失败），跳过偏差门
        log.warning("入场偏差门跳过（当前价格不可用）")
    # ═══ 偏差门结束 ═══

    # 2. 设置杠杆
    try:
        set_leverage(symbol, leverage)
        result["steps"].append({"step": "set_leverage", "status": "OK", "leverage": leverage})
        log.info(f"杠杆设置: {leverage}x ✅")
    except Exception as e:
        result["steps"].append({"step": "set_leverage", "status": "ERROR", "msg": str(e)})
        log.error(f"设置杠杆失败: {e}")
        return result

    # 3. 设置逐仓
    try:
        set_margin_type(symbol, "ISOLATED")
        result["steps"].append({"step": "set_margin", "status": "OK"})
        log.info("逐仓模式设置 ✅")
    except Exception as e:
        result["steps"].append({"step": "set_margin", "status": "ERROR", "msg": str(e)})
        log.error(f"设置逐仓失败: {e}")
        return result

    # 4. 市价开仓
    try:
        entry_side = "BUY" if direction == "long" else "SELL"
        pos_side = "LONG" if direction == "long" else "SHORT"
        order = place_order(symbol, entry_side, "MARKET", quantity=quantity,
                            position_side=pos_side)
        result["steps"].append({"step": "open_position", "status": "OK",
                                "order_id": order.get("orderId"),
                                "avg_price": order.get("avgPrice")})
        log.info(f"市价开仓成功 orderId={order.get('orderId')} ✅")
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_msg += f" | body: {e.response.text[:300]}"
            except Exception:
                pass
        result["steps"].append({"step": "open_position", "status": "ERROR", "msg": err_msg})
        log.error(f"开仓失败: {err_msg}")
        return result

    # ═══ 校验7: 滑点校准（按实际成交价等距平移止损止盈）═══
    actual_entry = float(order.get("avgPrice") or 0)
    if actual_entry <= 0:
        # avgPrice 不可用（币安市价单有时返回 null），查持仓获取入场价
        try:
            _positions = get_positions()
            _pos = next((p for p in _positions if p["symbol"] == symbol), None)
            if _pos:
                actual_entry = _pos["entry_price"]
                log.info(f"avgPrice 不可用，从持仓获取入场价: {actual_entry}")
        except Exception:
            pass
    if actual_entry > 0:
        delta = actual_entry - entry_price
        if abs(delta) > 0:
            # 等距平移：保持原计划的止损距离和R倍数不变
            stop_loss = stop_loss + delta
            for tp in take_profits:
                tp["price"] = tp["price"] + delta
            tp_str = '/'.join(f'{tp["price"]:.6g}' for tp in take_profits)
            log.info(f"滑点校准: 计划价 {entry_price} → 实际 {actual_entry}，"
                     f"平移 {delta:+.6g}，新止损 {stop_loss:.6g}，新TP {tp_str}")
            # ★ 写回计划文件（manage_position/detect_position_changes 读它匹配Algo挂单）
            try:
                plan["stop_loss"] = stop_loss
                plan["take_profits"] = take_profits
                plan["actual_entry"] = actual_entry
                plan["slippage"] = delta
                with open(plan_path, "w") as f:
                    json.dump(plan, f, indent=2, ensure_ascii=False)
                log.info("校准后价格已写回计划文件")
            except Exception as e:
                log.warning(f"写回计划文件失败（不影响挂单）: {e}")
    # ═══ 滑点校准结束 ═══

    # 5. 挂止损单
    try:
        exit_side = "SELL" if direction == "long" else "BUY"
        sl_order = _place_conditional_order(
            symbol, exit_side, "STOP_MARKET",
            stop_price=round_price(symbol, stop_loss),
            quantity=quantity, position_side=pos_side)
        result["steps"].append({"step": "stop_loss", "status": "OK",
                                "stop_price": stop_loss, "algo_id": sl_order.get("algoId")})
        log.info(f"止损单挂出 stopPrice={stop_loss} algoId={sl_order.get('algoId')} ✅")
    except Exception as e:
        result["steps"].append({"step": "stop_loss", "status": "ERROR", "msg": str(e)})
        log.error(f"挂止损失败，立即平仓防止裸仓: {e}")
        # ★ 保险买不上就退房：市价平掉刚开的仓，绝不留裸仓
        try:
            close_order = place_order(symbol, exit_side, "MARKET",
                                      quantity=quantity, position_side=pos_side)
            result["steps"].append({"step": "emergency_close", "status": "OK",
                                    "order_id": close_order.get("orderId")})
            log.info(f"止损挂失败 → 已紧急平仓 orderId={close_order.get('orderId')}")
        except Exception as e2:
            result["steps"].append({"step": "emergency_close", "status": "ERROR",
                                    "msg": str(e2)})
            log.error(f"紧急平仓也失败！{symbol} 可能裸仓，需立即手动处理！: {e2}")
        result["success"] = False
        return result

    # 6. 挂止盈单（分批）
    tp_results = []
    for i, tp in enumerate(take_profits):
        tp_price = tp["price"]
        reduce_pct = tp.get("reduce_percent", 50)
        tp_qty = round_qty(symbol, quantity * reduce_pct / 100)
        try:
            tp_order = _place_conditional_order(
                symbol, exit_side, "TAKE_PROFIT_MARKET",
                stop_price=round_price(symbol, tp_price),
                quantity=tp_qty, position_side=pos_side)
            tp_results.append({"tp": i + 1, "price": tp_price, "qty": tp_qty,
                               "algo_id": tp_order.get("algoId"), "status": "OK"})
            log.info(f"止盈 TP{i + 1} 挂出 price={tp_price} qty={tp_qty} algoId={tp_order.get('algoId')} ✅")
        except Exception as e:
            tp_results.append({"tp": i + 1, "price": tp_price, "qty": tp_qty,
                               "status": "ERROR", "msg": str(e)})
            log.error(f"挂止盈 TP{i + 1} 失败: {e}")

    result["steps"].append({"step": "take_profits", "results": tp_results})
    # ★ success 条件：止损必须挂上（止盈失败可容忍，还有止损兜着）
    sl_ok = any(s.get("step") == "stop_loss" and s.get("status") == "OK"
                for s in result["steps"])
    result["success"] = sl_ok
    result["executed_at"] = datetime.now(timezone.utc).isoformat()

    # 7. 保存执行记录
    history_file = os.path.join(HISTORY_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_{symbol}.json")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(history_file, "w") as f:
        json.dump({"plan": plan, "execution": result}, f, indent=2, ensure_ascii=False)
    log.info(f"执行记录已保存: {history_file}")

    log.info(f"═══ {symbol} 开仓完成 ✅ ═══")
    return result


# ─── 持仓管理 ──────────────────────────────────────────
def manage_position(symbol: str, plan: dict) -> dict:
    """
    检查持仓状态，处理 TP1 到达后的移保本操作。
    止损和止盈由交易所挂单自动执行，这里只做补充管理。
    """
    result = {"symbol": symbol, "actions": []}

    positions = get_positions()
    pos = next((p for p in positions if p["symbol"] == symbol), None)
    if not pos:
        # 无持仓时静默，不产生输出（避免 cron 每2分钟发无意义通知）
        return result

    mark_price = pos["mark_price"]
    amount = pos["amount"]
    direction = plan["direction"]
    pos_side = "LONG" if direction == "long" else "SHORT"
    entry_price = pos["entry_price"]

    take_profits = plan.get("take_profits", [])
    if len(take_profits) >= 1:
        tp1 = take_profits[0]
        tp1_price = tp1["price"]

        # 不依赖当前价格判断 TP1 是否触发，直接查 Algo 挂单状态：
        # - TP1 单还在 → 币安尚未执行，等待
        # - TP1 单消失 + 止损在原位 → 币安已执行 TP1，需移保本
        # - TP1 单消失 + 止损不在原位 → 已处理过
        algo_orders = get_open_algo_orders(symbol)
        sl_orders = [o for o in algo_orders if o.get("orderType") == "STOP_MARKET"
                     and o.get("side") == ("SELL" if direction == "long" else "BUY")]
        tp1_orders = [o for o in algo_orders if o.get("orderType") == "TAKE_PROFIT_MARKET"
                      and abs(float(o.get("triggerPrice", 0)) - tp1_price) < 0.0001 * tp1_price]

        original_sl = plan.get("stop_loss")
        sl_at_original = any(
            abs(float(o.get("triggerPrice", 0)) - original_sl) < 0.0001 * original_sl
            for o in sl_orders
        )

        if tp1_orders:
            # TP1 Algo 单还在 → 币安尚未执行，不干预，静默等待
            pass

        elif sl_at_original:
            # TP1 Algo 单已消失（币安已执行平仓）+ 止损还在原位
            # → 只需移保本，不再重复平仓
            log.info(f"{symbol} TP1 已由币安执行，执行移保本")
            exit_side = "SELL" if direction == "long" else "BUY"

            # 撤销旧止损（Algo 端点）
            for o in sl_orders:
                try:
                    api_delete("/fapi/v1/algoOrder", {"symbol": symbol, "algoId": str(o["algoId"])})
                except Exception:
                    pass

            # 挂新止损（保本 = 入场价，数量 = 当前剩余仓位）
            try:
                new_sl = round_price(symbol, entry_price)
                remaining_qty = abs(amount)
                _place_conditional_order(
                    symbol, exit_side, "STOP_MARKET",
                    stop_price=new_sl,
                    quantity=remaining_qty, position_side=pos_side)
                result["actions"].append({"action": "move_sl_to_breakeven",
                                          "new_sl": new_sl, "remaining_qty": remaining_qty, "status": "OK"})
                log.info(f"止损移到保本 {new_sl}（剩余 {remaining_qty}）✅")

                # ── 清理残留止盈单，按剩余仓位重新挂 ──
                # TP1 已被币安执行后，剩余 TP 单的数量仍按原始仓位计算，
                # 可能与实际持仓不匹配，需撤销后按剩余仓位重挂。
                # 此步骤为 best-effort：失败只记日志，不影响已挂好的保本止损。
                tp_orders = [o for o in algo_orders
                             if o.get("orderType") == "TAKE_PROFIT_MARKET"
                             and o.get("side") == exit_side]
                if tp_orders:
                    for o in tp_orders:
                        try:
                            api_delete("/fapi/v1/algoOrder",
                                       {"symbol": symbol, "algoId": str(o["algoId"])})
                        except Exception:
                            pass
                    # 未触发的 TP（TP2, TP3...），按剩余仓位比例重挂
                    remaining_tps = take_profits[1:]
                    if remaining_tps:
                        total_pct = sum(tp.get("reduce_percent", 0) for tp in remaining_tps)
                        allocated = 0.0
                        for i, tp in enumerate(remaining_tps):
                            if i == len(remaining_tps) - 1:
                                # 最后一个 TP 吃掉舍入误差，确保总数量 = 剩余仓位
                                tp_qty = round_qty(symbol, remaining_qty - allocated)
                            else:
                                pct = tp.get("reduce_percent", 0)
                                raw = remaining_qty * pct / total_pct if total_pct > 0 else 0
                                tp_qty = round_qty(symbol, raw)
                                allocated += tp_qty
                            if tp_qty <= 0:
                                continue
                            try:
                                _place_conditional_order(
                                    symbol, exit_side, "TAKE_PROFIT_MARKET",
                                    stop_price=round_price(symbol, tp["price"]),
                                    quantity=tp_qty, position_side=pos_side)
                                log.info(f"重挂 TP{i + 2} price={tp['price']} qty={tp_qty} ✅")
                            except Exception as e:
                                log.warning(f"重挂 TP{i + 2} 失败: {e}")
                    result["actions"].append({"action": "refresh_tp_orders",
                                              "remaining_tps": len(remaining_tps), "status": "OK"})

            except Exception as e:
                result["actions"].append({"action": "move_sl_to_breakeven", "status": "ERROR", "msg": str(e)})
        else:
            # TP1 单已消失 + 止损不在原位 → 已处理过，静默
            pass

    return result


# ─── 事件处理循环 ──────────────────────────────────────
def process_events() -> list:
    """扫描事件目录，处理所有待执行事件"""
    results = []
    if not os.path.isdir(EVENTS_DIR):
        return results

    for fname in sorted(os.listdir(EVENTS_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(EVENTS_DIR, fname)
        try:
            with open(fpath) as f:
                event = json.load(f)

            event_type = event.get("type", "")
            symbol = event.get("symbol", "")

            if event_type == "TRIGGER":
                # 找对应计划
                plan_file = os.path.join(PLANS_DIR, f"{symbol}-plan.json")
                if os.path.exists(plan_file):
                    log.info(f"处理触发事件: {symbol}")
                    r = execute_plan(plan_file)
                    results.append(r)
                    # 处理完删除事件文件
                    os.remove(fpath)
                else:
                    log.warning(f"找不到计划文件: {plan_file}")

            elif event_type == "TP1_HIT":
                plan_file = os.path.join(PLANS_DIR, f"{symbol}-plan.json")
                if os.path.exists(plan_file):
                    with open(plan_file) as f:
                        plan = json.load(f)
                    r = manage_position(symbol, plan)
                    results.append(r)
                    os.remove(fpath)

            elif event_type == "PLAN_EXPIRED":
                log.info(f"计划过期: {symbol}")
                plan_file = os.path.join(PLANS_DIR, f"{symbol}-plan.json")
                if os.path.exists(plan_file):
                    os.remove(plan_file)
                results.append({"symbol": symbol, "action": "expired", "cleaned": True})
                os.remove(fpath)

            elif event_type == "INVALIDATION":
                log.info(f"计划失效: {symbol}")
                plan_file = os.path.join(PLANS_DIR, f"{symbol}-plan.json")
                # ★ 有持仓时：不删计划文件（移保本/通知需要它），不撤单（止损止盈在保护仓位）
                #   无持仓时：正常清理（删计划文件 + 撤残留入场挂单）
                try:
                    positions = get_positions()
                    has_position = any(p["symbol"] == symbol for p in positions)
                except Exception as e:
                    log.warning(f"查询持仓失败，保守按有持仓处理: {symbol} ({e})")
                    has_position = True

                if has_position:
                    log.info(f"{symbol} 有活跃持仓，INVALIDATION 仅记录，不删计划不撤单")
                else:
                    if os.path.exists(plan_file):
                        os.remove(plan_file)
                    try:
                        cancel_all_orders(symbol)
                    except Exception:
                        pass
                    log.info(f"{symbol} 无持仓，已清理计划文件和残留挂单")
                results.append({"symbol": symbol, "action": "invalidated",
                                "had_position": has_position})
                os.remove(fpath)

        except Exception as e:
            log.error(f"处理事件 {fname} 失败: {e}")
            results.append({"file": fname, "error": str(e)})

    return results


def manage_all_positions() -> list:
    """遍历所有活跃计划，管理持仓"""
    results = []
    if not os.path.isdir(PLANS_DIR):
        return results
    for fname in os.listdir(PLANS_DIR):
        if not fname.endswith("-plan.json"):
            continue
        fpath = os.path.join(PLANS_DIR, fname)
        try:
            with open(fpath) as f:
                plan = json.load(f)
            symbol = plan["symbol"]
            r = manage_position(symbol, plan)
            if r["actions"]:
                results.append(r)
        except Exception as e:
            log.error(f"管理 {fname} 失败: {e}")
    return results


# ─── 持仓变动检测（止损/止盈/平仓通知）─────────────────
def _load_state() -> dict:
    """读取上次保存的持仓快照"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"positions": {}}


def _save_state(positions: list) -> None:
    """保存当前持仓快照"""
    state = {}
    for p in positions:
        state[p["symbol"]] = {
            "amount": p["amount"],
            "entry_price": p["entry_price"],
        }
    with open(STATE_FILE, "w") as f:
        json.dump({"positions": state}, f, ensure_ascii=False)


def detect_position_changes() -> list:
    """
    对比上次持仓快照和当前持仓，检测仓位变动并生成通知。
    独立函数，不修改任何现有逻辑。

    检测场景：
      - 仓位完全消失 → 止损/止盈/手动平仓
      - 仓位数量减少 → TP1 平半仓
    """
    notifications = []
    prev_state = _load_state()
    prev_positions = prev_state.get("positions", {})

    # 查当前持仓
    try:
        current_positions = get_positions()
    except Exception as e:
        log.warning(f"查询持仓失败，跳过变动检测: {e}")
        return notifications

    # 构建当前持仓字典
    current_map = {}
    for p in current_positions:
        current_map[p["symbol"]] = p

    # 对比：上次有，现在没了（或减少了）
    for symbol, prev in prev_positions.items():
        prev_amount = abs(prev.get("amount", 0))
        prev_entry = prev.get("entry_price", 0)

        if prev_amount == 0:
            continue

        current = current_map.get(symbol)
        current_amount = abs(current["amount"]) if current else 0

        if current_amount == 0 and prev_amount > 0:
            # ═══ 仓位完全消失 ═══
            # 判断平仓原因
            try:
                ticker = api_get("/fapi/v1/ticker/price", {"symbol": symbol})
                current_price = float(ticker["price"])
            except Exception:
                current_price = 0

            # 读计划文件获取止损/止盈价
            plan_file = os.path.join(PLANS_DIR, f"{symbol}-plan.json")
            stop_loss = None
            tp1_price = None
            # ★ 从持仓快照的带符号 amount 推断方向（正=多，负=空），不依赖计划文件
            direction = "long" if prev.get("amount", 0) > 0 else "short"
            if os.path.exists(plan_file):
                try:
                    with open(plan_file) as f:
                        plan = json.load(f)
                    stop_loss = plan.get("stop_loss")
                    tps = plan.get("take_profits", [])
                    if tps:
                        tp1_price = tps[0].get("price")
                except Exception:
                    pass

            # 计算盈亏
            if direction == "long":
                pnl = (current_price - prev_entry) * prev_amount
            else:
                pnl = (prev_entry - current_price) * prev_amount

            # 判断平仓类型（区分多空方向）
            if direction == "long":
                # 做多：止损在下方（价格跌破），止盈在上方（价格涨到）
                if stop_loss and current_price <= stop_loss * 1.002:
                    close_type = "止损"
                    emoji = "🔴"
                elif tp1_price and current_price >= tp1_price * 0.998:
                    close_type = "止盈"
                    emoji = "🟢"
                else:
                    close_type = "平仓"
                    emoji = "⚪"
            else:
                # 做空：止损在上方（价格涨破），止盈在下方（价格跌到）
                if stop_loss and current_price >= stop_loss * 0.998:
                    close_type = "止损"
                    emoji = "🔴"
                elif tp1_price and current_price <= tp1_price * 1.002:
                    close_type = "止盈"
                    emoji = "🟢"
                else:
                    close_type = "平仓"
                    emoji = "⚪"

            msg = (f"{emoji} {symbol} 已{close_type}\n"
                   f"入场: {prev_entry} → 当前: {current_price}\n"
                   f"盈亏: {pnl:+.2f}U")
            notifications.append({"symbol": symbol, "type": close_type,
                                  "pnl": round(pnl, 2), "message": msg})
            log.info(f"持仓变动: {msg}")

            # 清理：删除计划文件 + INVALIDATION 事件文件
            if os.path.exists(plan_file):
                os.remove(plan_file)
                log.info(f"已清理计划文件: {plan_file}")
            # 清理该币种的事件文件
            if os.path.isdir(EVENTS_DIR):
                for fname in os.listdir(EVENTS_DIR):
                    if fname.startswith(symbol) and fname.endswith(".json"):
                        fpath = os.path.join(EVENTS_DIR, fname)
                        try:
                            os.remove(fpath)
                        except Exception:
                            pass
            # 撤销该币种所有残留挂单（止损/止盈 Algo 单）
            try:
                cancel_all_orders(symbol)
                log.info(f"已撤销 {symbol} 所有残留挂单")
            except Exception as e:
                log.warning(f"撤销 {symbol} 残留挂单失败: {e}")

        elif 0 < current_amount < prev_amount * 0.8:
            # ═══ 仓位明显减少（TP1 平半仓）═══
            reduced_qty = prev_amount - current_amount
            try:
                ticker = api_get("/fapi/v1/ticker/price", {"symbol": symbol})
                current_price = float(ticker["price"])
            except Exception:
                current_price = 0

            direction = "long" if prev.get("amount", 0) > 0 else "short"
            if direction == "long":
                pnl = (current_price - prev_entry) * reduced_qty
            else:
                pnl = (prev_entry - current_price) * reduced_qty

            msg = (f"🟡 {symbol} 部分止盈\n"
                   f"已平: {reduced_qty} | 剩余: {current_amount}\n"
                   f"入场: {prev_entry} → 当前: {current_price}\n"
                   f"已实现盈亏: {pnl:+.2f}U")
            notifications.append({"symbol": symbol, "type": "partial_tp",
                                  "pnl": round(pnl, 2), "message": msg})
            log.info(f"持仓变动: {msg}")

    # 保存当前状态（供下次对比）
    _save_state(current_positions)

    return notifications


# ─── CLI 入口 ──────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="币安合约执行引擎")
    sub = parser.add_subparsers(dest="command")

    # 执行计划
    p_exec = sub.add_parser("execute", help="执行交易计划")
    p_exec.add_argument("--plan", required=True, help="计划 JSON 文件路径")

    # 处理事件
    sub.add_parser("process-events", help="扫描并处理事件目录")

    # 管理持仓
    sub.add_parser("manage", help="管理所有活跃持仓")

    # 查余额
    sub.add_parser("balance", help="查看账户余额")

    # 查持仓
    sub.add_parser("positions", help="查看当前持仓")

    # 撤所有单
    p_cancel = sub.add_parser("cancel-all", help="撤销某交易对所有挂单")
    p_cancel.add_argument("--symbol", required=True)
    p_cancel.add_argument("--force", action="store_true",
                          help="有持仓时也强制撤单（危险，慎用）")

    # 紧急平仓
    p_close = sub.add_parser("close", help="市价平仓")
    p_close.add_argument("--symbol", required=True)
    p_close.add_argument("--percent", type=float, default=100, help="平仓百分比")

    # 持仓变动检测
    sub.add_parser("watch", help="检测持仓变动（止损/止盈/平仓通知）")

    args = parser.parse_args()

    if args.command == "execute":
        r = execute_plan(args.plan)
        print(json.dumps(r, indent=2, ensure_ascii=False))

    elif args.command == "process-events":
        results = process_events()
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "manage":
        results = manage_all_positions()
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "balance":
        bal = get_balance()
        usdt = bal.get("USDT", {})
        print(f"USDT 余额: {usdt.get('balance', 0)} | 可用: {usdt.get('available', 0)}")

    elif args.command == "positions":
        positions = get_positions()
        if positions:
            for p in positions:
                print(f"{p['symbol']} | 数量: {p['amount']} | 入场: {p['entry_price']} "
                      f"| 标记: {p['mark_price']} | 盈亏: {p['unrealized_pnl']} "
                      f"| 杠杆: {p['leverage']}x | 强平: {p['liquidation_price']}")
        else:
            print("当前空仓")

    elif args.command == "cancel-all":
        results = cancel_all_orders(args.symbol, force=args.force)
        if not results and not args.force:
            print(f"⚠️ {args.symbol} 有持仓或查询失败，未撤单。加 --force 强制执行。")
        else:
            print(f"撤销 {len(results)} 个挂单")

    elif args.command == "close":
        positions = get_positions()
        pos = next((p for p in positions if p["symbol"] == args.symbol), None)
        if not pos:
            print(f"{args.symbol} 无持仓")
        else:
            amt = abs(pos["amount"]) * args.percent / 100
            side = "SELL" if pos["amount"] > 0 else "BUY"
            pos_side = "LONG" if pos["amount"] > 0 else "SHORT"
            qty = round_qty(args.symbol, amt)
            # Hedge Mode: positionSide 已锁定方向，不需要 reduceOnly（会触发 -1106）
            r = place_order(args.symbol, side, "MARKET", quantity=qty,
                            position_side=pos_side)
            print(f"平仓 {qty} {args.symbol} orderId={r.get('orderId')}")

    elif args.command == "watch":
        notifications = detect_position_changes()
        if notifications:
            for n in notifications:
                print(n["message"])
        # 无变动时不输出（静默）

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
