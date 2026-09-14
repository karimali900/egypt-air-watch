"""Egypt air watch dashboard — EN/AR, auto-refresh live picture."""
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from airwatch import store

st.set_page_config(page_title="Egypt Air Watch", layout="wide", page_icon="✈️")
st.markdown("""<style>
[data-testid="stAppViewContainer"] .block-container{padding:0.5rem 0.8rem;max-width:100%}
.air-hero{background:linear-gradient(120deg,#0f2a4a,#155a8a,#0e9a8a) !important;
  color:#fff !important;padding:24px 28px;border-radius:16px;margin-bottom:14px;}
.air-hero h1{margin:0 !important;font-size:24px !important;color:#fff !important;}
.air-hero p{margin:6px 0 0 !important;color:#e2e8f0 !important;font-size:14px;}
</style>""", unsafe_allow_html=True)

L10N = {
    "en": {"hero_t": "✈️ Egypt Air Watch — live airborne picture",
           "hero_s": "Real-time ADS-B tracks over Egypt (OpenSky, ~15 s refresh). NOT radar — aircraft broadcast positions.",
           "tracks": "Live tracks", "alerts": "Alerts", "replay": "Replay",
           "refresh": "Refresh (s)", "export": "Export snapshot CSV",
           "no_data": "No data yet — run: conda run -n petro python scripts/poll.py",
           "cols": ["Callsign", "ICAO", "Lat", "Lon", "Alt (m)", "Speed (m/s)", "HDG", "Squawk"]},
    "ar": {"hero_t": "✈️ المراقبة الجوية المصرية — صورة حية",
           "hero_s": "مواقع الطائرات لحظياً فوق مصر (OpenSky، تحديث ~15 ثانية). ليست راداراً — الطائرات تبث مواقعها.",
           "tracks": "الرحلات الحية", "alerts": "التنبيهات", "replay": "إعادة التشغيل",
           "refresh": "التحديث (ثانية)", "export": "تصدير CSV",
           "no_data": "لا بيانات بعد — شغّل: conda run -n petro python scripts/poll.py",
           "cols": ["الرحلة", "الكود", "العرض", "الطول", "الارتفاع (م)", "السرعة (م/ث)", "الاتجاه", "سكواك"]},
}

lang = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"], index=0)
t = L10N["ar" if lang == "العربية" else "en"]
if lang == "العربية":
    st.markdown('<style>html,body,[data-testid="stAppViewContainer"]{direction:rtl;text-align:right}</style>', unsafe_allow_html=True)

import yaml
cfg = yaml.safe_load(open(ROOT / "config" / "zones.yaml"))

st.markdown(f"""<div class="air-hero">
<h1>{t["hero_t"]}</h1><p>{t["hero_s"]}</p></div>""",
            unsafe_allow_html=True)

ref = st.sidebar.slider(t["refresh"], 5, 120, 15, key="ref")

con = store.connect(ROOT / cfg.get("db", "data/tracks.db"))
tracks = store.latest_snapshot(con)
alerts = store.recent_alerts(con, 30)

if not tracks:
    st.info(t["no_data"])
else:
    df = pd.DataFrame(tracks)
    k1, k2, k3 = st.columns(3)
    k1.metric(t["tracks"], len(df))
    k2.metric(t["alerts"], len(alerts))
    ages = (time.time() - df["snapshot"].max()) if len(df) else 999
    k3.metric("age (s)", f"{ages:.0f}")
    try:
        import json as _json
        _fs = _json.loads((ROOT / "data" / "feed_status.json").read_text())
        _fage = time.time() - _fs.get("ts", 0)
        _st = _fs.get("state", "?")
        if _st == "ok" and _fage < 900:
            st.success(f"● LIVE — feed ok ({_fs.get('tracks', 0)} tracks, {_fage:.0f}s ago)"
                       if lang != "العربية" else
                       f"● مباشر — البث يعمل ({_fs.get('tracks', 0)} رحلة، قبل {_fage:.0f} ث)")
        elif _st == "ratelimit":
            st.warning("● FEED LIMITED — OpenSky quota exhausted, retrying automatically"
                       if lang != "العربية" else
                       "● البث محدود — حصة OpenSky انتهت، تتم إعادة المحاولة تلقائياً")
        else:
            st.error(f"● FEED {_st.upper()} — {_fs.get('detail', '')} ({_fage:.0f}s ago)"
                     if lang != "العربية" else
                     f"● البث {_st} — {_fs.get('detail', '')} (قبل {_fage:.0f} ث)")
    except Exception:
        st.caption("feed status: unknown (poll.py not reporting yet)")
    if ages > 120:
        st.warning("STALE DATA — snapshot is {:.0f} min old. Restart scripts/poll.py for live positions.".format(ages / 60)
                   if lang != "العربية" else
                   "بيانات قديمة — اللقطة عمرها {:.0f} دقيقة. أعد تشغيل scripts/poll.py للمواقع الحية.".format(ages / 60))

    tab_map, tab_tbl, tab_al = st.tabs([t["tracks"], t["alerts"], t["replay"]])
    with tab_map:
        import numpy as np
        import plotly.express as px
        import plotly.graph_objects as go
        from PIL import Image
        emg = df[df["squawk"].isin(cfg.get("alerts", {}).get("emergency_squawks", []))]
        labels = df["callsign"].where(df["callsign"] != "", df["icao24"])
        c1, c2 = st.columns([1, 1])
        with c1:
            _show_labels = st.checkbox("labels" if lang != "العربية" else "التسميات",
                                       value=True, key="air_labels")
        with c2:
            _view = st.radio("map" if lang != "العربية" else "الخريطة",
                             ["Vector" if lang != "العربية" else "متجهة",
                              "Satellite" if lang != "العربية" else "قمر صناعي"],
                             horizontal=True, key="air_view", label_visibility="collapsed")
        _sat = str(_view).lower().startswith("sat") or "قمر" in str(_view)
        _bb = cfg["bbox"]

        @st.cache_data(ttl=3600)
        def _basemap():
            import json as _json
            _bp, _bj = ROOT / "data" / "basemap_sat.png", ROOT / "data" / "basemap_sat.json"
            if not (_bp.exists() and _bj.exists()):
                return None
            _g = _json.loads(_bj.read_text())
            _raw = np.asarray(Image.open(_bp).convert("RGB"))
            # Unambiguous in EVERY plotly.js: ascending axes, row 0 = south,
            # origin lower. (Descending-y + origin upper flips in some
            # renderers — that was the upside-down bug.)
            _img = _raw[::-1]
            _xs = np.linspace(_g["wlon"], _g["elon"], _img.shape[1])
            _ys = np.linspace(_g["slat"], _g["nlat"], _img.shape[0])
            return _img, _xs, _ys

        fig = go.Figure()
        _bm = _basemap() if _sat else None
        if _bm is not None:
            _img, _xs, _ys = _bm
            fig = px.imshow(_img, x=_xs, y=_ys, origin="lower", aspect="equal")
            fig.update_layout(height=900, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor="#0b1526",
                              xaxis=dict(visible=True, range=[_bb[0], _bb[2]],
                                         showticklabels=True, tickfont=dict(size=10, color="white"),
                                         ticks="", gridcolor="rgba(255,255,255,.15)",
                                         tickformat=".0f", title="°E"),
                              yaxis=dict(visible=True, range=[_bb[1], _bb[3]],
                                         showticklabels=True, tickfont=dict(size=10, color="white"),
                                         ticks="", gridcolor="rgba(255,255,255,.15)",
                                         tickformat=".0f", title="°N"))
            fig.add_annotation(x=_bb[2] - 0.3, y=_bb[3] - 0.3, text="N 🡅",
                               showarrow=False, font=dict(size=22, color="white"),
                               bgcolor="rgba(11,21,38,.65)",
                               borderpad=6)
            _ink = "white"
        elif _sat:
            fig.update_layout(height=900, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor="#0b1526",
                              xaxis=dict(visible=False, range=[_bb[0], _bb[2]]),
                              yaxis=dict(visible=False, range=[_bb[1], _bb[3]]))
            _ink = "white"
        else:
            # initial vector view (offline geography, no tiles)
            fig.update_layout(height=900, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor="#dcebf8",
                              geo=dict(scope="africa", projection_type="mercator",
                                       center=dict(lat=27, lon=30),
                                       lonaxis=dict(range=[_bb[0] - 1, _bb[2] + 1]),
                                       lataxis=dict(range=[_bb[1] - 1, _bb[3] + 1]),
                                       showland=True, landcolor="#e8f3e4",
                                       showocean=True, oceancolor="#bcd7f0",
                                       showcountries=True, countrycolor="#94a3b8"))
            _ink = "#0f2a4a"
        _XY = dict(x=df["lon"], y=df["lat"]) if _sat else dict(lon=df["lon"], lat=df["lat"])
        _EXY = dict(x=emg["lon"], y=emg["lat"]) if _sat else dict(lon=emg["lon"], lat=emg["lat"])
        _APXY = lambda d: (dict(x=d["lon"], y=d["lat"]) if _sat else dict(lon=d["lon"], lat=d["lat"]))
        _Scatter = go.Scatter if _sat else go.Scattergeo
        # motion trails from stored history (visible movement even between polls)
        try:
            for _ico in df["icao24"].unique().tolist()[:60]:
                _h = store.track_history(con, _ico, 8)
                if len(_h) > 1:
                    _tl = ([p["lon"] for p in _h], [p["lat"] for p in _h])
                    _td = dict(x=_tl[0], y=_tl[1]) if _sat else dict(lon=_tl[0], lat=_tl[1])
                    fig.add_trace(_Scatter(**_td, mode="lines",
                                             line=dict(width=2, color="rgba(251,191,36,.55)"),
                                             hoverinfo="skip", showlegend=False))
        except Exception:
            pass
        fig.add_trace(_Scatter(**_XY,
                                 mode="markers+text" if _show_labels else "markers",
                                 marker=dict(size=12, color="#fbbf24",
                                             line=dict(width=2, color="black")),
                                 text=labels, textposition="top center",
                                 textfont=dict(size=9, color=_ink),
                                 hovertemplate="%{text}<br>alt %{customdata[0]:.0f} m<br>spd %{customdata[1]:.0f} m/s<br>hdg %{customdata[2]}<extra></extra>",
                                 customdata=df[["baro_alt", "velocity", "heading"]].fillna(0).values))
        if not emg.empty:
            fig.add_trace(_Scatter(**_EXY, mode="markers",
                                     marker=dict(size=20, color="red", symbol="x",
                                                 line=dict(width=3, color="white")),
                                     hoverinfo="skip", showlegend=False))
        ap = pd.DataFrame(cfg.get("airports", []))
        if not ap.empty:
            fig.add_trace(_Scatter(**_APXY(ap), mode="markers+text",
                                     marker=dict(size=8, color="#38bdf8", symbol="square",
                                                 line=dict(width=1, color="white")),
                                     text=ap["code"], textposition="bottom center",
                                     textfont=dict(size=10, color=_ink),
                                     hoverinfo="skip", showlegend=False))
        st.plotly_chart(fig, use_container_width=True,
                        config={"scrollZoom": True, "displaylogo": False})
        _bb2 = cfg["bbox"]
        st.caption(f"{len(df)} tracks • snapshot {pd.to_datetime(df['snapshot'].max(), unit='s').strftime('%H:%M:%S')} UTC • "
                   f"frame {_bb2[0]}–{_bb2[2]}E, {_bb2[1]}–{_bb2[3]}N (Egypt + neighbours) • "
                   "empty areas = no ADS-B tracks received there, not no aircraft • trails = last 8 positions"
                   if lang != "العربية" else
                   f"{len(df)} رحلة • اللقطة {pd.to_datetime(df['snapshot'].max(), unit='s').strftime('%H:%M:%S')} • "
                   f"الإطار {_bb2[0]}–{_bb2[2]} شرقاً، {_bb2[1]}–{_bb2[3]} شمالاً (مصر + الجيران) • "
                   "المناطق الفارغة = لا إشارات مستلمة هناك • الخطوط = آخر 8 مواقع")
    with tab_tbl:
        show = df[["callsign", "icao24", "lat", "lon", "baro_alt", "velocity", "heading", "squawk"]].copy()
        show.columns = t["cols"]
        st.dataframe(show, hide_index=True, use_container_width=True)
        st.download_button(t["export"], show.to_csv(index=False).encode(),
                           file_name="snapshot_latest.csv", mime="text/csv")
    with tab_al:
        if not alerts:
            st.caption("—")
        else:
            adf = pd.DataFrame(alerts)
            adf["time"] = pd.to_datetime(adf["ts"], unit="s").dt.strftime("%H:%M:%S")
            st.dataframe(adf[["time", "kind", "callsign", "icao24", "detail"]],
                         hide_index=True, use_container_width=True)

time.sleep(ref)
st.rerun()
