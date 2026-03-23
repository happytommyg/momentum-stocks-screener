import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# ============================================================
# 設定
# ============================================================
st.set_page_config(page_title="リーダー株スクリーナー", layout="wide")

SHOW_TOP_N = 15
WINDOW_6M  = 126
WINDOW_3M  = 63
WINDOW_1M  = 21

# ============================================================
# 銘柄リスト取得
# ============================================================
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

# ============================================================
# 価格データ取得 & リターン計算
# ============================================================
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
    r1m = df.pct_change(WINDOW_1M, fill_method=None).iloc[-1]

    result = pd.DataFrame({"6ヶ月騰落率": r6m, "3ヶ月騰落率": r3m, "1ヶ月騰落率": r1m})
    result = result.dropna()
    return result, base_date

# ============================================================
# 段階スクリーニング
# ============================================================
def screen(returns_df, top_n):
    step1 = returns_df["6ヶ月騰落率"].nlargest(top_n * 4).index
    step2 = returns_df.loc[step1, "3ヶ月騰落率"].nlargest(top_n * 2).index
    step3 = returns_df.loc[step2, "1ヶ月騰落率"].nlargest(top_n).index
    return returns_df.loc[step3].sort_values("6ヶ月騰落率", ascending=False)

# ============================================================
# UI
# ============================================================
st.title("リーダー株スクリーナー")
st.caption("6ヶ月→3ヶ月→1ヶ月の騰落率で段階スクリーニング")

col_left, col_right = st.columns([1, 2])

with col_left:
    index_choice = st.selectbox("対象指数", ["S&P500", "NASDAQ-100", "両方"])
    top_n = st.slider("表示件数", min_value=5, max_value=30, value=SHOW_TOP_N, step=5)
    run = st.button("スクリーニング実行", type="primary", use_container_width=True)

# ============================================================
# 実行
# ============================================================
if run:
    indexes = (
        ["S&P500", "NASDAQ-100"] if index_choice == "両方"
        else [index_choice]
    )

    for idx in indexes:
        st.subheader(idx)
        with st.spinner(f"{idx} の銘柄データを取得中..."):
            tickers = get_tickers(idx)
            if not tickers:
                st.error("銘柄リストを取得できませんでした")
                continue

            returns_df, base_date = calc_returns(tickers)
            if returns_df is None:
                st.error("価格データを取得できませんでした")
                continue

        st.caption(f"基準日: {base_date}　対象: {len(returns_df)}銘柄")

        result = screen(returns_df, top_n)

        # TradingViewリンクを追加
        result = result.copy()
        result.index.name = "銘柄"
        result = result.reset_index()
        result["TradingView"] = result["銘柄"].apply(
            lambda t: f"https://www.tradingview.com/chart/?symbol=NASDAQ:{t}"
        )

        # 色付け関数
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

        ret_cols = ["6ヶ月騰落率", "3ヶ月騰落率", "1ヶ月騰落率"]

       styled = (
            result.style
            .applymap(color_cell, subset=ret_cols)
            .format({col: lambda x: f"{x*100:+.1f}%" for col in ret_cols})
        )

        st.dataframe(
            styled,
            column_config={
                "TradingView": st.column_config.LinkColumn(
                    "TradingView",
                    display_text="チャートを見る"
                )
            },
            use_container_width=True,
            height=min(400, (top_n + 1) * 35 + 10),
            hide_index=True,
        )

        st.divider()

else:
    st.info("左のパネルで設定して「スクリーニング実行」を押してください。")

# ============================================================
# フッター
# ============================================================
st.markdown(
    "<p style='font-size:11px;color:gray;margin-top:2rem;'>"
    "データ: Yahoo Finance（yfinance）。投資判断は自己責任でお願いします。"
    "</p>",
    unsafe_allow_html=True,
)
