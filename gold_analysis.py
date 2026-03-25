"""
gold_analysis.py — Professional 4H XAU/USD technical analysis for Trade 2 Win bot.
Returns (analysis_text, chart_png_bytes).

Indicators computed on 4H candles:
  - RSI (14)
  - EMA 50 & EMA 200  (Golden / Death Cross)
  - Bollinger Bands (SMA20, ±2σ)
  - Pivot-based Support & Resistance from last 100 candles
  - Supply & Demand zone labels
  - Combined buy / sell / wait recommendation
"""

import io
import logging
import datetime

logger = logging.getLogger(__name__)

TRADINGVIEW_URL = "https://www.tradingview.com/chart/?symbol=OANDA:XAUUSD&interval=240"


# ─── Data helpers ────────────────────────────────────────────────────────────

def _resample_4h(df):
    """Aggregate 1H OHLCV dataframe into 4H candles."""
    import pandas as pd
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample("4h").agg(agg).dropna()


def _rsi(close, period: int = 14):
    """Wilder smoothed RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


# ─── Support / Resistance ─────────────────────────────────────────────────────

def _cluster(levels: list, pct: float = 0.003) -> list:
    """Remove duplicate levels within `pct` distance of each other."""
    levels = sorted(set(levels))
    out = []
    for lvl in levels:
        if not out or (lvl - out[-1]) / out[-1] > pct:
            out.append(lvl)
    return out


def _find_sr(df, candles: int = 100, order: int = 4, top_n: int = 2):
    """
    Pivot-point detection on the last `candles` bars.
    Returns (supports_list, resistances_list) sorted nearest to current price.
    Falls back to rolling min/max if too few pivots are found.
    """
    import numpy as np
    tail = df.tail(candles)
    lows  = tail["Low"].values
    highs = tail["High"].values
    price = float(tail["Close"].iloc[-1])

    raw_sup, raw_res = [], []
    for i in range(order, len(tail) - order):
        if lows[i]  == np.min(lows[i - order : i + order + 1]):
            raw_sup.append(round(float(lows[i]), 2))
        if highs[i] == np.max(highs[i - order : i + order + 1]):
            raw_res.append(round(float(highs[i]), 2))

    sups_all = _cluster(raw_sup)
    ress_all = sorted(_cluster(raw_res), reverse=True)

    sups = sorted([s for s in sups_all if s < price], reverse=True)[:top_n]
    ress = [r for r in ress_all if r > price][:top_n]

    # Fallback when pivot detection yields too few levels
    if len(sups) < top_n:
        fb = sorted({
            round(float(df["Low"].rolling(20).min().iloc[-1]), 2),
            round(float(df["Low"].rolling(50).min().iloc[-1]), 2),
        }, reverse=True)
        sups = (sups + [s for s in fb if s not in sups and s < price])[:top_n]

    if len(ress) < top_n:
        fb = sorted({
            round(float(df["High"].rolling(20).max().iloc[-1]), 2),
            round(float(df["High"].rolling(50).max().iloc[-1]), 2),
        })
        ress = (ress + [r for r in fb if r not in ress and r > price])[:top_n]

    return sups, ress


# ─── Recommendation ──────────────────────────────────────────────────────────

def _recommend(rsi: float, price: float, ema50: float, ema200: float,
               bb_lower: float, bb_upper: float) -> tuple[str, str]:
    score = 0
    reasons = []

    if price > ema50 > ema200:
        score += 2; reasons.append("السعر فوق EMA50 وEMA200")
    elif price < ema50 < ema200:
        score -= 2; reasons.append("السعر تحت EMA50 وEMA200")
    elif price > ema50:
        score += 1
    elif price < ema50:
        score -= 1

    if rsi < 35:
        score += 1; reasons.append(f"RSI في ذروة البيع ({rsi})")
    elif rsi > 65:
        score -= 1; reasons.append(f"RSI في ذروة الشراء ({rsi})")

    if price <= bb_lower:
        score += 1; reasons.append("السعر عند حد بولينجر السفلي")
    elif price >= bb_upper:
        score -= 1; reasons.append("السعر عند حد بولينجر العلوي")

    reason_str = " · ".join(reasons) if reasons else "السوق في توازن"

    if score >= 2:
        return "شراء 🟢 (Buy)", reason_str
    if score <= -2:
        return "بيع 🔴 (Sell)", reason_str
    return "انتظار ⚪ (Wait)", reason_str


# ─── Main entry point ─────────────────────────────────────────────────────────

def get_gold_analysis() -> tuple[str, bytes | None]:
    """
    Fetch live XAU/USD data, compute 4H technical analysis,
    generate a mplfinance chart, and return (text_report, png_bytes).
    png_bytes is None on chart failure.
    """
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import mplfinance as mpf
    except ImportError as exc:
        return f"⚠️ مكتبة مفقودة: {exc}", None

    # ── Fetch 1H data and resample → 4H ──────────────────────────────────────
    try:
        ticker  = yf.Ticker("GC=F")
        df_raw  = ticker.history(period="60d", interval="1h")
        if df_raw.empty:
            df_raw = ticker.history(period="500d", interval="1d")
            df_raw = df_raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df_raw.index = pd.to_datetime(df_raw.index)
            if df_raw.index.tz is not None:
                df_raw.index = df_raw.index.tz_localize(None)
            df = df_raw
        else:
            df_raw = df_raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df     = _resample_4h(df_raw)
    except Exception as exc:
        logger.error(f"Gold data fetch error: {exc}")
        return f"⚠️ خطأ في جلب البيانات: {exc}", None

    if len(df) < 30:
        return "⚠️ البيانات غير كافية لإجراء التحليل. حاول لاحقاً.", None

    close = df["Close"]

    # ── Price change ──────────────────────────────────────────────────────────
    current_price = round(float(close.iloc[-1]), 2)
    prev_price    = round(float(close.iloc[-2]), 2)
    change        = round(current_price - prev_price, 2)
    change_pct    = round((change / prev_price) * 100, 2)

    # ── RSI 14 ────────────────────────────────────────────────────────────────
    rsi_series = _rsi(close, 14)
    rsi        = round(float(rsi_series.iloc[-1]), 1)

    # ── EMA 50 & EMA 200 ─────────────────────────────────────────────────────
    ema50  = round(float(close.ewm(span=50,  adjust=False).mean().iloc[-1]), 2)
    ema200 = round(float(close.ewm(span=200, adjust=False).mean().iloc[-1]), 2)

    # ── Bollinger Bands (20, 2σ) ─────────────────────────────────────────────
    sma20    = close.rolling(20).mean()
    std20    = close.rolling(20).std()
    bb_upper = round(float((sma20 + 2 * std20).iloc[-1]), 2)
    bb_mid   = round(float(sma20.iloc[-1]), 2)
    bb_lower = round(float((sma20 - 2 * std20).iloc[-1]), 2)
    bb_width = round((bb_upper - bb_lower) / bb_mid * 100, 1)

    # ── Support / Resistance ──────────────────────────────────────────────────
    supports, resistances = _find_sr(df, candles=min(100, len(df)))

    # ── Trend & Cross labels ──────────────────────────────────────────────────
    if abs(ema50 - ema200) / ema200 < 0.002:
        cross_label = "على وشك التقاطع ⚡"
        trend_label = "محايد ↔️"
    elif ema50 > ema200:
        cross_label = "تقاطع ذهبي ✨ (Golden Cross)"
        trend_label = "صاعد (Bullish) 📈"
    else:
        cross_label = "تقاطع الموت 💀 (Death Cross)"
        trend_label = "هابط (Bearish) 📉"

    # ── RSI label ─────────────────────────────────────────────────────────────
    if rsi >= 70:
        rsi_label = f"{rsi} — ذروة شراء ⚠️ (Overbought)"
    elif rsi <= 30:
        rsi_label = f"{rsi} — ذروة بيع ⚠️ (Oversold)"
    elif rsi >= 60:
        rsi_label = f"{rsi} — قوي 📈 (Strong)"
    elif rsi <= 40:
        rsi_label = f"{rsi} — ضعيف 📉 (Weak)"
    else:
        rsi_label = f"{rsi} — محايد ✅ (Neutral)"

    # ── Volatility label ──────────────────────────────────────────────────────
    if bb_width > 3.5:
        vol_label = f"مرتفعة ⚡ ({bb_width}%)"
    elif bb_width < 1.0:
        vol_label = f"منخفضة 😴 ({bb_width}%)"
    else:
        vol_label = f"متوسطة 📊 ({bb_width}%)"

    # ── Supply / Demand zones ─────────────────────────────────────────────────
    if len(supports) >= 2:
        demand_zone = f"${min(supports):,.2f} — ${max(supports):,.2f}"
    elif supports:
        demand_zone = f"${supports[0]:,.2f}"
    else:
        demand_zone = "غير محدد"

    if len(resistances) >= 2:
        supply_zone = f"${min(resistances):,.2f} — ${max(resistances):,.2f}"
    elif resistances:
        supply_zone = f"${resistances[0]:,.2f}"
    else:
        supply_zone = "غير محدد"

    # ── Recommendation ────────────────────────────────────────────────────────
    rec_action, rec_reason = _recommend(rsi, current_price, ema50, ema200, bb_lower, bb_upper)

    direction_emoji = "🟢" if change >= 0 else "🔴"
    change_str      = f"+{change}" if change >= 0 else str(change)
    now_utc         = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    sup_str = "  |  ".join(f"${s:,.2f}" for s in sorted(supports))
    res_str = "  |  ".join(f"${r:,.2f}" for r in sorted(resistances))

    text = (
        f"📊 التحليل الفني — الذهب XAU/USD (4H)\n"
        f"🕐 {now_utc}\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ السعر الحالي:  ${current_price:,.2f}\n"
        f"{direction_emoji} التغيير:  {change_str}$ ({change_pct:+.2f}%)\n\n"
        f"📈 الاتجاه العام (4H):  {trend_label}\n"
        f"🔀 نوع التقاطع:  {cross_label}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ مستويات الدعم:  {sup_str or 'N/A'}\n"
        f"⚔️ مستويات المقاومة:  {res_str or 'N/A'}\n\n"
        f"🟦 منطقة الطلب (Demand):  {demand_zone}\n"
        f"🟥 منطقة العرض (Supply):  {supply_zone}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 مؤشر RSI (14):  {rsi_label}\n"
        f"📊 EMA 50:  ${ema50:,.2f}   |   EMA 200:  ${ema200:,.2f}\n"
        f"📉 بولينجر العلوي:  ${bb_upper:,.2f}   |   السفلي:  ${bb_lower:,.2f}\n"
        f"💨 تذبذب السوق (BB Width):  {vol_label}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 التوصية الفنية:  {rec_action}\n"
        f"📝 {rec_reason}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ هذا التحليل للأغراض التعليمية فقط.\n"
        "التداول ينطوي على مخاطر — تصرّف بحذر."
    )

    # ── Chart ─────────────────────────────────────────────────────────────────
    chart_bytes = None
    try:
        plot_df = df.tail(80).copy()
        cl      = plot_df["Close"]

        ema50_line  = cl.ewm(span=50,  adjust=False).mean()
        ema200_line = cl.ewm(span=200, adjust=False).mean()
        sma20_line  = cl.rolling(20).mean()
        std20_line  = cl.rolling(20).std()
        bb_up_line  = sma20_line + 2 * std20_line
        bb_lo_line  = sma20_line - 2 * std20_line
        rsi_line    = _rsi(cl, 14)

        ap = [
            mpf.make_addplot(ema50_line,  color="#f39c12", width=1.6, label="EMA 50"),
            mpf.make_addplot(ema200_line, color="#9b59b6", width=2.0, label="EMA 200"),
            mpf.make_addplot(bb_up_line,  color="#5dade2", width=0.9,
                             linestyle="dashed", label="BB Upper"),
            mpf.make_addplot(bb_lo_line,  color="#5dade2", width=0.9,
                             linestyle="dashed", label="BB Lower"),
            mpf.make_addplot(sma20_line,  color="#aaaaaa", width=0.7,
                             linestyle="dotted"),
        ]

        # S/R horizontal lines (limit to 2+2 to avoid clutter)
        for lvl in supports[:2]:
            ap.append(mpf.make_addplot(
                [lvl] * len(plot_df), color="#26a69a",
                linestyle="--", width=0.9, secondary_y=False,
            ))
        for lvl in resistances[:2]:
            ap.append(mpf.make_addplot(
                [lvl] * len(plot_df), color="#ef5350",
                linestyle="--", width=0.9, secondary_y=False,
            ))

        # RSI panel (panel 2)
        ap.append(mpf.make_addplot(
            rsi_line, panel=2, color="#e74c3c", ylabel="RSI", ylim=(0, 100),
        ))
        ap.append(mpf.make_addplot(
            [70.0] * len(plot_df), panel=2,
            color="#e74c3c", linestyle="--", width=0.7, secondary_y=False,
        ))
        ap.append(mpf.make_addplot(
            [30.0] * len(plot_df), panel=2,
            color="#26a69a", linestyle="--", width=0.7, secondary_y=False,
        ))

        mc = mpf.make_marketcolors(
            up="#26a69a", down="#ef5350",
            edge="inherit", wick="inherit", volume="in",
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            base_mpf_style="nightclouds",
            gridstyle="--",
            gridcolor="#2a2a3e",
            facecolor="#12122a",
            figcolor="#12122a",
            rc={
                "axes.labelcolor": "#cccccc",
                "xtick.color":     "#999999",
                "ytick.color":     "#999999",
            },
        )

        title_str = (
            f"\nXAU/USD — 4H  |  ${current_price:,.2f}  "
            f"|  RSI {rsi}  |  {trend_label}"
        )
        buf = io.BytesIO()
        mpf.plot(
            plot_df,
            type="candle",
            style=style,
            addplot=ap,
            title=title_str,
            ylabel="Price (USD)",
            volume=True,
            panel_ratios=(4, 1, 1.8),
            figsize=(13, 8),
            savefig=dict(fname=buf, dpi=130, bbox_inches="tight"),
            warn_too_much_data=9999,
        )
        buf.seek(0)
        chart_bytes = buf.read()
        plt.close("all")
    except Exception as exc:
        logger.warning(f"Chart generation error: {exc}")

    return text, chart_bytes
