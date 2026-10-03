"""Macro Quant Lab dashboard (Streamlit).

Run locally:   streamlit run app/streamlit_app.py
Free hosting:  Streamlit Community Cloud, main file app/streamlit_app.py
Reads the repo's data folder when run locally, otherwise the public files on GitHub.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/Oblivion783/macro-quant-lab/main"
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]

st.set_page_config(page_title="Macro Quant Lab", layout="wide")


@st.cache_data(ttl=3600)
def read_text(rel: str) -> str | None:
    p = ROOT / rel
    if p.exists():
        return p.read_text(encoding="utf-8")
    r = requests.get(f"{RAW}/{rel}", timeout=30)
    return r.text if r.status_code == 200 else None


@st.cache_data(ttl=3600)
def series(sid: str) -> pd.Series:
    txt = read_text(f"data/history/{sid}.csv")
    if not txt:
        return pd.Series(dtype=float, name=sid)
    df = pd.read_csv(io.StringIO(txt), parse_dates=["date"])
    return df.set_index("date")["value"].rename(sid)


cfg = yaml.safe_load(read_text("config/series.yaml") or "series: []")
meta = {s["id"]: s for s in cfg.get("series", [])}
for d in cfg.get("derived", []):
    meta[d["id"]] = {**d, "source": "derived"}
snap_txt = read_text("data/latest/snapshot.json")
snap = json.loads(snap_txt) if snap_txt else {"asof": "–", "series": []}

st.title("Macro Quant Lab")
st.caption(f"Snapshot as of {snap['asof']}. Personal research on public data; not investment advice.")

tab1, tab2, tab3, tab4 = st.tabs(["Snapshot", "Charts", "Decoder", "Model portfolio"])

with tab1:
    df = pd.DataFrame(snap["series"])
    if df.empty:
        st.info("No snapshot yet. The daily job writes one every weekday morning.")
    else:
        groups = sorted(df["group"].unique())
        pick = st.multiselect("Groups", groups, default=groups)
        view = df[df["group"].isin(pick)][["name", "unit", "last", "chg_1d", "chg_1w", "chg_1m", "z_1y", "date"]]
        st.dataframe(view.rename(columns={"chg_1d": "1d", "chg_1w": "1w", "chg_1m": "1m", "z_1y": "z (1y)"}),
                     hide_index=True, use_container_width=True)
        st.caption("pct: level %, change bp · spread: bp · price: change % · level: change in points")

with tab2:
    ids = [k for k in meta if k not in ("UST_1M", "UST_6M", "UST_1Y", "UST_3Y", "UST_7Y", "UST_20Y")]
    names = {k: meta[k]["name"] for k in ids}
    chosen = st.multiselect("Series (up to three, same unit)", ids, default=["UST_10Y", "UK_10Y", "EUR_10Y"],
                            format_func=lambda k: names[k], max_selections=3)
    years = st.slider("Years", 1, 8, 2)
    index100 = st.checkbox("Index to 100 at start", value=False)
    fig = go.Figure()
    for k, sid in enumerate(chosen):
        if meta[sid].get("source") == "derived":
            s = series(meta[sid]["a"]) - series(meta[sid]["b"])
        else:
            s = series(sid)
        s = s[s.index >= s.index.max() - pd.DateOffset(years=years)] if not s.empty else s
        if index100 and not s.empty:
            s = s / s.iloc[0] * 100
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=names[sid], line=dict(width=2, color=COLORS[k])))
    fig.update_layout(height=460, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, use_container_width=True)
    units = {meta[s]["unit"] for s in chosen}
    if len(units) > 1:
        st.warning("These series have different units; tick 'Index to 100' or compare them on separate charts.")

with tab3:
    idx = read_text("docs/decoder/index.md")
    st.markdown(idx or "No decodes yet.")

with tab4:
    nav_txt = read_text("data/portfolio/nav.csv")
    if not nav_txt:
        st.info("The paper portfolio goes live on 1 January 2027.")
    else:
        nav = pd.read_csv(io.StringIO(nav_txt), parse_dates=["date"]).set_index("date")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=nav.index, y=nav["nav"], name="Model portfolio", line=dict(width=2, color=COLORS[0])))
        fig.add_trace(go.Scatter(x=nav.index, y=nav["bench_nav"], name="60/40 benchmark", line=dict(width=2, color=COLORS[1])))
        fig.update_layout(height=420, hovermode="x unified", legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, use_container_width=True)
        w = nav[[c for c in nav if c.startswith("w_")]].iloc[-1].rename(lambda c: c[2:])
        st.bar_chart(w)
