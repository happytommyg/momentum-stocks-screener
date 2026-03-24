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

# セクターETFマップ（騰落率計算用）
SECTOR_ETFS = {
    "情報技術":     "XLK",
    "半導体":       "SOXX",
    "エネルギー":   "XLE",
    "素材":         "XLB",
    "資本財":       "XLI",
    "金融":         "XLF",
    "ヘルスケア":   "XLV",
    "生活必需品":   "XLP",
    "通信":         "XLC",
    "公益":         "XLU",
    "不動産":       "XLRE",
    "一般消費財":   "XLY",
}

# 銘柄→セクターマップ
TICKER_SECTOR = {
    # 半導体・テクノロジー
    "MU":"半導体","AMAT":"半導体","LRCX":"半導体","KLAC":"半導体",
    "NVDA":"半導体","AMD":"半導体","INTC":"半導体","MRVL":"半導体",
    "AVGO":"半導体","TSM":"半導体","ASML":"半導体","TER":"半導体",
    "SNDK":"情報技術","WDC":"情報技術","STX":"情報技術",
    "CIEN":"情報技術","KEYS":"情報技術","DELL":"情報技術",
    "GEV":"資本財","HON":"資本財","MMM":"資本財","GLW":"資本財",
    # エネルギー
    "APA":"エネルギー","HAL":"エネルギー","SLB":"エネルギー",
    "BKR":"エネルギー","VLO":"エネルギー","MPC":"エネルギー",
    "DVN":"エネルギー","FANG":"エネルギー","XOM":"エネルギー",
    "CVX":"エネルギー","COP":"エネルギー","OXY":"エネルギー",
    "EOG":"エネルギー","PSX":"エネルギー","TRGP":"エネルギー",
    # 素材
    "CF":"素材","LYB":"素材","DOW":"素材","NEM":"素材",
    # 金融
    "JPM":"金融","BAC":"金融","GS":"金融","MS":"金融",
    # ヘルスケア
    "MRNA":"ヘルスケア","AMGN":"ヘルスケア","GILD":"ヘルスケア",
    # 生活必需品
    "COST":"生活必需品","WMT":"生活必需品","SBUX":"生活必需品",
    # 一般消費財
    "ABNB":"一般消費財","TSLA":"一般消費財",
    # 通信
    "META":"通信","GOOGL":"通信","GOOG":"通信",
    # 公益
    "AEP":"公益","EXC":"公益","XEL":"公益",
    # 資本財・運輸
    "DAL":"資本財","ODFL":"資本財","FIX":"資本財",
    # その他
    "TPL":"エネルギー","ARM":"半導体","ROST":"一般消費財",
    "WMT":"生活必需品","LIN":"素材","TXN":"半導体",
    "CSX":"資本財","FAST":"資本財","ADI":"半導体",
    "MAR":"一般消費財","HON":"資本財","MPWR":"半導体",
}

SECTOR_COLORS = {
    "半導体":     "#1D9E75",
    "情報技術":   "#7F77DD",
    "エネルギー": "#378ADD",
    "素材":       "#D85A30",
    "資本財":     "#EF9F27",
    "金融":       "#D4537E",
    "ヘルスケア": "#5DCAA5",
    "生活必需品": "#888780",
    "通信":       "#AFA9EC",
    "公益":       "#97C459",
    "不動産":     "#F0997B",
    "一般消費財": "#FAC775",
}

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

@st.cache_data(ttl=60 * 60 * 6)
def calc_sector_returns():
    etf_list = list(SECTOR_ETFS.values())
    start = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    df_raw = yf.download(etf_list, start=start, auto_adjust=True,
                         group_by="ticker", progress=False, threads=True)
    results = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            s = df_raw[etf]["Close"].dropna()
            if len(s) > WINDOW_6M:
                r6m = (s.iloc[-1] / s.iloc[-WINDOW_6M] - 1) * 100
                r3m = (s.iloc[-1] / s.iloc[-WINDOW_3M] - 1) * 100
                results[sector] = {"6ヶ月": round(r6m, 1), "3ヶ月": round(r3m, 1)}
        except Exception:
            continue
    return pd.DataFrame(results).T

def screen(returns_df, top_n):
    step1 = returns_df["6ヶ月騰落率"].nlargest(top_n * 4).index
    step2 = returns_df.loc[step1, "3ヶ月騰落率"].nlargest(top_n).index
    return returns_df.loc[step2].sort_values("6ヶ月騰落率", ascending=False)

def get_sector(ticker):
    return TICKER_SECTOR.get(ticker, "その他")

def sector_score(sector, sector_df):
    if sector not in sector_df.index:
        return None
    r6 = sector_df.loc[sector, "6ヶ月"]
    r3 = sector_df.loc[sector, "3ヶ月"]
    # 6ヶ月60% + 3ヶ月40%の加重スコア
    score = r6 * 0.6 + r3 * 0.4
    return round(score, 1)

def score_label(score):
    if score is None:
        return "—"
    if score >= 30:
        return f"🔥 {score:+.1f}pt"
    elif score >= 15:
        return f"↑ {score:+.1f}pt"
    elif score >= 0:
        return f"→ {score:+.1f}pt"
    else:
        return f"↓ {score:+.1f}pt"

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

# session_state初期化
if "results" not in st.session_state:
    st.session_state.results = {}
if "sector_df" not in st.session_state:
    st.session_state.sector_df = None
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None

st.title("リーダー株スクリーナー")
st.caption("セクター分析 → 個別銘柄のトップダウンアプローチ")

with st.sidebar:
    index_choice = st.selectbox("対象指数", ["S&P500", "NASDAQ-100", "両方"])
    top_n = st.slider("表示件数", min_value=5, max_value=30, value=SHOW_TOP_N, step=5)
    run = st.button("スクリーニング実行", type="primary", use_container_width=True)

if run:
    st.session_state.selected_ticker = None
    st.session_state.results = {}

    # Step1: セクター騰落率
    with st.spinner("セクターデータを取得中..."):
        st.session_state.sector_df = calc_sector_returns()

    # Step2: 個別銘柄
    indexes = ["S&P500", "NASDAQ-100"] if index_choice == "両方" else [index_choice]
    for idx in indexes:
        with st.spinner(f"{idx} の銘柄データを取得中..."):
            tickers = get_tickers(idx)
            if not tickers:
                continue
            returns_df, base_date = calc_returns(tickers)
            if returns_df is None:
                continue
        result = screen(returns_df, top_n)
        result = result.copy()
        result.index.name = "銘柄"
        result = result.reset_index()
        result["TradingView"] = result["銘柄"].apply(
            lambda t: f"https://www.tradingview.com/chart/?symbol={t}"
        )
        st.session_state.results[idx] = (result, base_date, len(returns_df))

# ==================== 表示 ====================
if st.session_state.sector_df is not None and not st.session_state.sector_df.empty:
    sdf = st.session_state.sector_df.copy()

    st.subheader("Step 1 ｜ セクター別騰落率")
    st.caption("強いセクターのリーダー株を狙う")

    # 6ヶ月順でソート
    sdf_sorted = sdf.sort_values("6ヶ月", ascending=False)

    # カード表示
    cols = st.columns(4)
    for i, (sector, row) in enumerate(sdf_sorted.iterrows()):
        color = SECTOR_COLORS.get(sector, "#888780")
        r6 = row["6ヶ月"]
        r3 = row["3ヶ月"]
        icon = "🔥" if r6 >= 30 else "↑" if r6 >= 10 else "→" if r6 >= 0 else "↓"
        with cols[i % 4]:
            st.markdown(
                f"""<div style="border:0.5px solid {color}44;border-left:3px solid {color};
                border-radius:8px;padding:10px 12px;margin-bottom:10px;
                background:var(--color-background-primary)">
                <div style="font-size:11px;color:{color};font-weight:500">{icon} {sector}</div>
                <div style="font-size:18px;font-weight:500;color:var(--color-text-primary)">
                {r6:+.1f}%</div>
                <div style="font-size:11px;color:var(--color-text-secondary)">
                3ヶ月: {r3:+.1f}%</div></div>""",
                unsafe_allow_html=True
            )

    st.divider()

if st.session_state.results:
    st.subheader("Step 2 ｜ 個別銘柄ランキング")

    for idx, (result, base_date, total) in st.session_state.results.items():
        st.markdown(f"**{idx}**　<span style='font-size:12px;color:gray'>基準日: {base_date}　対象: {total}銘柄</span>",
                    unsafe_allow_html=True)

        # セクター列・スコア列を追加
        sdf = st.session_state.sector_df
        result["セクター"] = result["銘柄"].apply(get_sector)
        result["セクター強度"] = result["銘柄"].apply(
            lambda t: score_label(sector_score(get_sector(t), sdf))
        )

        ret_cols = ["6ヶ月騰落率", "3ヶ月騰落率"]
        fmt = {col: lambda x: f"{x*100:+.1f}%" for col in ret_cols}
        styled = result.style.applymap(color_cell, subset=ret_cols).format(fmt)

        st.dataframe(
            styled,
            column_config={
                "TradingView": st.column_config.LinkColumn(
                    "TradingView", display_text="チャートを見る"
                ),
                "セクター強度": st.column_config.TextColumn(
                    "セクター強度", help="セクターETFの6ヶ月×60%+3ヶ月×40%の加重スコア"
                ),
            },
            column_order=["銘柄", "セクター", "セクター強度", "6ヶ月騰落率", "3ヶ月騰落率", "TradingView"],
            use_container_width=True,
            height=min(500, (len(result) + 1) * 35 + 10),
            hide_index=True,
        )

        # 銘柄ボタン
        st.markdown("**気になる銘柄をクリック：**")
        cols = st.columns(8)
        for i, ticker in enumerate(result["銘柄"].tolist()):
            with cols[i % 8]:
                if st.button(ticker, key=f"btn_{idx}_{ticker}"):
                    st.session_state.selected_ticker = ticker
        st.divider()

    # 選択銘柄パネル
    if st.session_state.selected_ticker:
        ticker = st.session_state.selected_ticker
        sector = get_sector(ticker)
        sdf = st.session_state.sector_df
        sc = sector_score(sector, sdf)

        st.subheader(f"📌 {ticker}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**セクター:** {sector}")
            if sc is not None:
                st.markdown(f"**セクター強度スコア:** {score_label(sc)}")
        with c2:
            st.link_button("TradingViewでチャートを見る",
                           f"https://www.tradingview.com/chart/?symbol={ticker}",
                           use_container_width=True)
            st.link_button("Yahoo Financeで詳細を見る",
                           f"https://finance.yahoo.com/quote/{ticker}",
                           use_container_width=True)

        st.code(
            f"{ticker} について教えてください。どんな会社で、なぜ最近株価が強いのか教えてください。",
            language=None
        )

elif not run:
    st.info("左のパネルで設定して「スクリーニング実行」を押してください。")

st.markdown(
    "<p style='font-size:11px;color:gray;margin-top:2rem;'>"
    "データ: Yahoo Finance（yfinance）。投資判断は自己責任でお願いします。"
    "</p>",
    unsafe_allow_html=True,
)
