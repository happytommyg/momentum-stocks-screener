import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="リーダー株スクリーナー", layout="wide")

SHOW_TOP_N = 15
WINDOW_6M  = 126
WINDOW_3M  = 63

@st.cache_data(ttl=60 * 60 * 24)
def get_tickers(index_name):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if index_name == "S&P500":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            df = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return [s.replace(".", "-") for s in df["Symbol"].tolist()]
        elif index_name == "NASDAQ-100":
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            dfs = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            for d in dfs:
                if "Ticker" in d.columns:
                    return [s.replace(".", "-") for s in d["Ticker"].tolist()]
                if "Symbol" in d.columns:
                    return [s.replace(".", "-") for s in d["Symbol"].tolist()]
    except Exception as e:
        st.error(f"銘柄リスト取得エラー: {e}")
    return []

@st.cache_data(ttl=60 * 60 * 6)
def calc_returns(tickers):
    start = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    df_raw = yf.download(
        tickers, start=start, auto_adjust=True,
        group_by="ticker", progress=False, threads=True
    )
    if df_raw.empty:
        return None, None
    close_dict = {}
    for t in tickers:
        try:
            if t in df_raw.columns.levels[0]:
                s = df_raw[t]["Close"].dropna()
                if len(s) > WINDOW_6M:
                    close_dict[t] = s
        except Exception:
            continue
    df = pd.DataFrame(close_dict)
    base_date = df.index[-1].strftime("%Y-%m-%d")
    r6m = df.pct_change(WINDOW_6M, fill_method=None).iloc[-1]
    r3m = df.pct_change(WINDOW_3M, fill_method=None).iloc[-1]
    result = pd.DataFrame({"6ヶ月騰落率": r6m, "3ヶ月騰落率": r3m})
    result = result.dropna()
    return result, base_date

def screen(returns_df, top_n):
    step1 = returns_df["6ヶ月騰落率"].nlargest(top_n * 4).index
    step2 = returns_df.loc[step1, "3ヶ月騰落率"].nlargest(top_n).index
    return returns_df.loc[step2].sort_values("6ヶ月騰落率", ascending=False)

def color_cell(val):
    try:
        v = float(val) * 100
        if v >= 10:
            return "background-color: #c6efce; color: #276221"
        elif v >= 0:
            return "background-color: #e9f5e9; color: #1a5c1a"
        elif v >= -5:
            return "background-color: #fff2cc; color: #7d6608"
        else:
            return "background-color: #fce4e4; color: #9c2a2a"
    except Exception:
        return ""

st.title("リーダー株スクリーナー")
st.caption("6ヶ月→3ヶ月の騰落率で段階スクリーニング")

with st.sidebar:
    index_choice = st.selectbox("対象指数", ["S&P500", "NASDAQ-100", "両方"])
    top_n = st.slider("表示件数", min_value=5, max_value=30, value=SHOW_TOP_N, step=5)
    run = st.button("スクリーニング実行", type="primary", use_container_width=True)

# 銘柄選択の状態管理
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None

if run:
    st.session_state.selected_ticker = None
    indexes = ["S&P500", "NASDAQ-100"] if index_choice == "両方" else [index_choice]
    all_results = {}

    for idx in indexes:
        with st.spinner(f"{idx} の銘柄データを取得中..."):
            tickers = get_tickers(idx)
            if not tickers:
                st.error("銘柄リストを取得できませんでした")
                continue
            returns_df, base_date = calc_returns(tickers)
            if returns_df is None:
                st.error("価格データを取得できませんでした")
                continue
        all_results[idx] = (returns_df, base_date)

    for idx, (returns_df, base_date) in all_results.items():
        st.subheader(idx)
        st.caption(f"基準日: {base_date}　対象: {len(returns_df)}銘柄")
        result = screen(returns_df, top_n)
        result = result.copy()
        result.index.name = "銘柄"
        result = result.reset_index()
        result["TradingView"] = result["銘柄"].apply(
            lambda t: f"https://www.tradingview.com/chart/?symbol={t}"
        )

        ret_cols = ["6ヶ月騰落率", "3ヶ月騰落率"]
        fmt = {col: lambda x: f"{x*100:+.1f}%" for col in ret_cols}
        styled = result.style.applymap(color_cell, subset=ret_cols).format(fmt)

        st.dataframe(
            styled,
            column_config={
                "TradingView": st.column_config.LinkColumn("TradingView", display_text="チャートを見る")
            },
            use_container_width=True,
            height=min(500, (top_n + 1) * 35 + 10),
            hide_index=True,
        )

        # 「Claudeに聞く」ボタンを銘柄ごとに表示
        st.markdown("**気になる銘柄をClaudeに聞く：**")
        cols = st.columns(min(top_n, 8))
        for i, ticker in enumerate(result["銘柄"].tolist()):
            with cols[i % min(top_n, 8)]:
                if st.button(ticker, key=f"{idx}_{ticker}"):
                    st.session_state.selected_ticker = ticker

        st.divider()

# 選択された銘柄の情報を表示
if st.session_state.selected_ticker:
    ticker = st.session_state.selected_ticker
    st.subheader(f"{ticker} について")
    st.markdown(f"""
この銘柄についてClaudeに質問するには、以下をコピーしてClaudeのチャットに貼り付けてください：

> **{ticker} について教えてください。どんな会社で、なぜ最近株価が強いのか教えてください。**
""")
    col1, col2 = st.columns(2)
    with col1:
        st.link_button(
            f"TradingViewでチャートを見る",
            f"https://www.tradingview.com/chart/?symbol={ticker}",
            use_container_width=True
        )
    with col2:
        st.link_button(
            f"Yahoo Financeで詳細を見る",
            f"https://finance.yahoo.com/quote/{ticker}",
            use_container_width=True
        )

st.markdown(
    "<p style='font-size:11px;color:gray;margin-top:2rem;'>"
    "データ: Yahoo Finance（yfinance）。投資判断は自己責任でお願いします。"
    "</p>",
    unsafe_allow_html=True,
)
