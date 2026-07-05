"""Scan Dashboard — market regime badge + results table + score breakdown."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import get_market_regime, get_stock_scan, get_strategies, sync_yahoo_data, get_stock_chart


@st.dialog("📈 Chart")
def chart_dialog(ticker):
    st.caption(f"**{ticker}** — Candlestick with EMA 8/21, JNSAR, MACD")
    with st.spinner(f"Loading chart for {ticker}..."):
        chart_data = get_stock_chart(ticker, 100)

    if "error" in chart_data or not chart_data.get("candles"):
        st.error(chart_data.get("error", "No chart data available"))
    else:
        candles = chart_data["candles"]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])

        fig.add_trace(go.Candlestick(
            x=[c["date"] for c in candles], open=[c["open"] for c in candles],
            high=[c["high"] for c in candles], low=[c["low"] for c in candles],
            close=[c["close"] for c in candles], name=ticker,
        ), row=1, col=1)

        fig.add_trace(go.Scatter(x=[c["date"] for c in candles], y=[c["ema8"] for c in candles],
            mode="lines", name="EMA 8", line=dict(color="#636efa", width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=[c["date"] for c in candles], y=[c["ema21"] for c in candles],
            mode="lines", name="EMA 21", line=dict(color="#ef553b", width=1)), row=1, col=1)

        jnsar_vals = [c["jnsar"] for c in candles]
        fig.add_trace(go.Scatter(x=[c["date"] for c in candles], y=jnsar_vals,
            mode="lines", name="JNSAR", line=dict(color="#ffa15a", width=1, dash="dot")), row=1, col=1)

        dates_m = [c["date"] for c in candles]
        macd_l = [c["macd_line"] for c in candles]
        macd_s = [c["macd_signal"] for c in candles]
        macd_h = [c["macd_histogram"] for c in candles]
        colors = ["#00cc96" if h >= 0 else "#ef553b" for h in macd_h]
        fig.add_trace(go.Bar(x=dates_m, y=macd_h, name="MACD Hist", marker_color=colors), row=2, col=1)
        fig.add_trace(go.Scatter(x=dates_m, y=macd_l, mode="lines", name="MACD Line",
            line=dict(color="#636efa", width=1)), row=2, col=1)
        fig.add_trace(go.Scatter(x=dates_m, y=macd_s, mode="lines", name="Signal",
            line=dict(color="#ef553b", width=1)), row=2, col=1)

        fig.update_layout(height=500, xaxis_rangeslider_visible=False,
                          template="plotly_dark", hovermode="x unified")
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="MACD", row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)

        last = candles[-1]
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        mcol1.metric("Close", last["close"])
        mcol2.metric("High", last["high"])
        mcol3.metric("Low", last["low"])
        mcol4.metric("Volume", f"{last['volume']:,}")

    if st.button("✕ Close"):
        st.session_state.chart_ticker = None
        st.rerun()


def show():
    st.session_state.setdefault("chart_ticker", None)
    st.title("🔍 Scan Dashboard")

    # Sync trigger in sidebar
    with st.sidebar:
        st.markdown("### 🔄 Data Sync")
        st.caption(f"DB: `database/quantscanner.duckdb`")
        if st.button("Sync Yahoo Finance Data", type="secondary", use_container_width=True,
                     help="Downloads ~1yr of daily data for all 867 stocks from Yahoo Finance"):
            with st.spinner("Syncing all stocks from Yahoo Finance... (this takes ~5-10 min)"):
                result = sync_yahoo_data()
            if result["status"] == "completed":
                st.success(f"✅ Synced {result['synced']}/{result['total']} tickers")
                if result["errors"]:
                    with st.expander(f"⚠️ {len(result['errors'])} errors"):
                        for e in result["errors"][:20]:
                            st.code(e)
            else:
                st.error("Sync failed")
            st.rerun()

    with st.spinner("Loading market regime..."):
        regime = get_market_regime()

    col1, col2, col3 = st.columns(3)
    r = regime["market_regime"]
    badge = "🟢 BULLISH" if r == "BULLISH" else ("🔴 BEARISH" if r == "BEARISH" else "⚪ UNKNOWN")
    col1.metric("Market Regime", badge)
    col2.metric("Nifty 50", regime["index_close"])
    col3.metric("200 EMA", regime["index_ema200"])

    strategies = get_strategies()
    selected = st.selectbox("Strategy Filter", strategies, index=0)

    if st.button("Run Scan", type="primary", use_container_width=True):
        with st.spinner("Scanning 867 stocks..."):
            data = get_stock_scan(selected)

        if not data["results"]:
            st.warning("No results match the selected strategy.")
            st.session_state.scan_results = None
            st.session_state.chart_ticker = None
        else:
            st.success(f"Found {len(data['results'])} matching stocks (scored {data['total_scored']} total)")
            st.session_state.scan_results = data["results"]
    else:
        st.info("Select a strategy and click **Run Scan** to begin.")

    # Results table — click any row to open chart popup
    if st.session_state.get("scan_results"):
        results = st.session_state.scan_results
        rows = []
        for r in results:
            rows.append({
                "Ticker": r["ticker"], "Sector": r["sector"],
                "Price": r["price"], "Score": r["score"],
                "Strategy": r["strategy"], "Conviction": r["conviction"],
                "RSI": r["rsi14"], "ADX": r["adx14"],
                "Z-Score": r["z_score"], "52W Disc%": r["discount_52w"],
                "Stop": r["stop_loss"], "Target": r["target1"],
            })

        df = pd.DataFrame(rows)
        tbl_key = f"scan_tbl_{st.session_state.get('_st', 0)}"
        sel = st.dataframe(df, key=tbl_key, use_container_width=True, height=500,
                           column_config={
                               "Score": st.column_config.NumberColumn(format="%d"),
                               "Price": st.column_config.NumberColumn(format="%.2f"),
                               "RSI": st.column_config.NumberColumn(format="%.1f"),
                               "ADX": st.column_config.NumberColumn(format="%.1f"),
                               "Z-Score": st.column_config.NumberColumn(format="%.2f"),
                               "52W Disc%": st.column_config.NumberColumn(format="%.1f%%"),
                               "Stop": st.column_config.NumberColumn(format="%.2f"),
                               "Target": st.column_config.NumberColumn(format="%.2f"),
                           },
                           on_select="rerun", selection_mode="single-row")
        if sel and hasattr(sel, 'selection') and sel.selection and sel.selection.rows:
            row_idx = sel.selection.rows[0]
            ticker = results[row_idx]["ticker"]
            st.session_state.chart_ticker = ticker
            st.session_state._st = st.session_state.get("_st", 0) + 1
            st.rerun()

        # Detail expander for first few tickers
        with st.expander("📊 Score Breakdown (Top 5)"):
            for r in results[:5]:
                cols = st.columns(7)
                cols[0].metric("Trend", r["trend_score"], help="Max 20")
                cols[1].metric("RS", r["rs_score"], help="Max 20")
                cols[2].metric("Vol Acc", r["vol_acc_score"], help="Max 10")
                cols[3].metric("Vol Setup", r["vol_setup_score"], help="Max 10")
                cols[4].metric("Momentum", r["momentum_score"], help="Max 10")
                cols[5].metric("Institutional", r["inst_score"], help="Max 10")
                cols[6].metric("Total", r["score"])
                st.caption(f"**{r['ticker']}** — {r['strategy']} ({r['conviction']})")
                st.divider()

    # Open chart popup when a ticker is selected
    if st.session_state.chart_ticker:
        chart_dialog(st.session_state.chart_ticker)
