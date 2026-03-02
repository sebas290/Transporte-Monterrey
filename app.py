# -------------------------------------------------------------
# Tablero Interactivo (Streamlit) – estilo Canva + tiempo real
# Esquema A: ANIO, ID_MES, TRANSPORTE, VARIABLE, VALOR, ...
# Esquema B: ANIO, ID_MES, TRANSPORTE, AUTOBUSES, PASAJEROS, MES
# + Monitoreo (CSV simulado) con auto-rerun suave (st.rerun)
# + Bubble chart limitado a Metrobús / Transmetro / Transmetro G-M-G
# + Fijes clave: normalización de VARIABLE y fix de mojibake
# -------------------------------------------------------------

import os
import re
import time
import random
import threading
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.io as pio

import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, HeatMap

st.set_page_config(page_title="Tablero Interactivo – Transporte", layout="wide")

# =============================================================
# 🎨 Branding / Tema (ajusta colores a tu Canva)
# =============================================================
BRAND = {
    "PRIMARY":  "#DC3912",  # rojo acento
    "SECONDARY":"#109618",  # verde
    "TERTIARY": "#3366CC",  # azul
    "BG":       "#0E1117",  # fondo
    "SURFACE":  "#161A23",  # tarjetas/paneles
    "TEXT":     "#E6E8EB",  # texto principal
    "MUTED":    "#A6A9AF",  # texto secundario
}

# CSS global (tipografía + componentes)
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {{
  --brand-primary:{BRAND["PRIMARY"]}; --brand-secondary:{BRAND["SECONDARY"]}; --brand-tertiary:{BRAND["TERTIARY"]};
  --brand-bg:{BRAND["BG"]}; --brand-surface:{BRAND["SURFACE"]}; --brand-text:{BRAND["TEXT"]}; --brand-muted:{BRAND["MUTED"]};
}}
html, body, [data-testid="stAppViewContainer"] {{
  font-family:'Inter', system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif;
  background:var(--brand-bg); color:var(--brand-text);
}}
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, rgba(22,26,35,0.92), rgba(14,17,23,0.98) 60%);
  border-right: 1px solid rgba(255,255,255,0.04);
}}
h1, h2, h3, h4 {{ letter-spacing:.2px; font-weight:700; }}
h1 strong, h2 strong {{ color:var(--brand-primary); }}
.block-container {{ padding-top: 1.0rem; }}
div[data-testid="stMetric"] {{
  background:var(--brand-surface); border:1px solid rgba(255,255,255,0.06);
  border-radius:14px; padding:14px 16px; box-shadow:0 4px 18px rgba(0,0,0,0.25);
}}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {{ transform:scale(1.05); }}
.stButton>button, button[kind="secondary"] {{
  background:var(--brand-primary); color:#fff; border:none; border-radius:10px; font-weight:600;
  box-shadow:0 6px 16px rgba(220,57,18,0.35);
}}
.stButton>button:hover {{ filter:brightness(1.05); }}
hr {{ border:none; border-top:1px solid rgba(255,255,255,0.06); margin:1.0rem 0; }}
.badge {{
  display:inline-flex; align-items:center; gap:.45rem; background:rgba(255,255,255,0.06);
  border:1px solid rgba(255,255,255,0.07); color:var(--brand-muted); padding:.35rem .6rem; border-radius:999px;
  font-size:.80rem; line-height:1;
}}
.badge--primary {{ background:rgba(220,57,18,.12); color:#FFD3C9; border-color:rgba(220,57,18,.28); }}
</style>
""", unsafe_allow_html=True)

# Plantilla Plotly (oscura para el resto de gráficos)
pio.templates["rob_dark"] = pio.templates["plotly_dark"]
pio.templates["rob_dark"].layout.update(
    font=dict(family="Inter, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif",
              size=14, color=BRAND["TEXT"]),
    paper_bgcolor=BRAND["BG"], plot_bgcolor=BRAND["SURFACE"],
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,0.06)", borderwidth=0),
    colorway=[BRAND["PRIMARY"], BRAND["SECONDARY"], BRAND["TERTIARY"], "#F2C037", "#8B6DFC"]
)
DEFAULT_TEMPLATE = "rob_dark"

# Encabezado tipo "hero"
st.markdown(
    """
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:.25rem;">
      <span class="badge badge--primary">Dashboard</span>
      <span class="badge">Live</span>
    </div>
    <h1 style="margin:0 0 .25rem 0;">Monitoreo de Transporte <strong>AMG</strong></h1>
    <div style="color:var(--brand-muted); margin-bottom:1.0rem;">
      Visual • Interactivo • Actualización en tiempo real
    </div>
    """, unsafe_allow_html=True
)

# =============================================================
# Utilidades de tiempo (meses)
# =============================================================
SPANISH_MONTHS = {
    "01": ("Enero", "Ene"), "02": ("Febrero", "Feb"), "03": ("Marzo", "Mar"),
    "04": ("Abril", "Abr"), "05": ("Mayo", "May"), "06": ("Junio", "Jun"),
    "07": ("Julio", "Jul"), "08": ("Agosto", "Ago"), "09": ("Septiembre", "Sep"),
    "10": ("Octubre", "Oct"), "11": ("Noviembre", "Nov"), "12": ("Diciembre", "Dic"),
}
_NAME_TO_NUM = {
    "enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
    "julio":"07","agosto":"08","septiembre":"09","setiembre":"09","octubre":"10","noviembre":"11","diciembre":"12",
    "ene":"01","feb":"02","mar":"03","abr":"04","may":"05","jun":"06","jul":"07","ago":"08","sep":"09","oct":"10","nov":"11","dic":"12",
}
def _strip_accents_lower(s: str) -> str:
    if not isinstance(s, str): s = str(s) if s is not None else ""
    mapping = str.maketrans("áéíóúÁÉÍÓÚüÜ", "aeiouAEIOUuU")
    return s.translate(mapping).strip().lower()

def month_name_to_num(name: str) -> Optional[str]:
    return _NAME_TO_NUM.get(_strip_accents_lower(name))

def num_to_month_name(num2: str, short=True) -> str:
    num2 = str(num2).zfill(2)
    full, short3 = SPANISH_MONTHS.get(num2, (num2, num2))
    return short3 if short else full

# =============================================================
# Utilidades de texto (mojibake + normalización)
# =============================================================
import unicodedata

def _deaccent(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))

def _fix_mojibake_text(s: str) -> str:
    """Corrige los patrones de mojibake más comunes que trae el CSV."""
    s = str(s)
    # intento de round-trip si vienen bytes mal interpretados
    try:
        s2 = s.encode("latin1", "ignore").decode("utf-8", "ignore")
        if any(ch in s for ch in ("Ã","Â","¢","¿","¡","©")):
            s = s2
    except Exception:
        pass
    # reemplazos dirigidos que observamos en el archivo
    rep = {
        "operacia3n": "operacion",
        "operaciÃ³n": "operacion", "operaciaÃ³n": "operacion",
        "sa¡bado": "sabado", "sÃ¡bado": "sabado",
        "kila3metros": "kilometros", "kilÃ³metros": "kilometros",
        "energa": "energia", "energÃ­a": "energia",
        "ela©ctrica": "electrica", "elÃ©ctrica": "electrica",
    }
    for k, v in rep.items():
        s = s.replace(k, v)
    return s

def normalize_variable_series(s: pd.Series) -> pd.Series:
    """Normaliza VARIABLE: quita BOM/espacios, corrige mojibake, quita acentos y baja a minúsculas."""
    return (s.astype(str)
              .str.replace("\ufeff", "", regex=False)
              .str.replace(r"\s+", " ", regex=True)
              .apply(_fix_mojibake_text)
              .apply(_deaccent)
              .str.lower().str.strip())

# =============================================================
# Carga/Limpieza del CSV principal (soporta A/B)
# =============================================================
@st.cache_data(show_spinner=False)
def load_csv_any(path_or_buffer) -> pd.DataFrame:
    try:
        df = pd.read_csv(path_or_buffer, encoding="latin1")
    except Exception:
        df = pd.read_csv(path_or_buffer, encoding="utf-8", sep=",")

    def _clean_col(col):
        col = str(col)
        col = col.replace("\ufeff", "").replace("ï»¿", "").strip().strip('"').strip("'")
        return col
    df.columns = [_clean_col(c) for c in df.columns]
    df.columns = [c.lower() for c in df.columns]

    for col in df.columns:
        if col in ["anio", "id_mes", "id_entidad", "id_municipio"]:
            df[col] = df[col].astype(str).str.replace(r"\s+", "", regex=True)
            df.loc[df[col].isin(["", "nan", "None"]), col] = np.nan

    if "anio" in df.columns:
        df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")

    if "mes" in df.columns and "id_mes" not in df.columns:
        df["id_mes"] = df["mes"].astype(str).map(lambda x: month_name_to_num(x) or x).astype(str)
    if "id_mes" in df.columns:
        df["id_mes"] = df["id_mes"].astype(str)
        df["id_mes"] = df["id_mes"].apply(lambda x: month_name_to_num(x) if not x.isdigit() else x)
        df["id_mes"] = df["id_mes"].astype(str).str.zfill(2)
        df["mes_nombre"] = df["id_mes"].apply(lambda x: num_to_month_name(x, short=False))

    cols = set(df.columns)
    has_schema_b = {"autobuses", "pasajeros", "transporte", "anio", "id_mes"}.issubset(cols)
    has_schema_a = {"variable", "valor", "transporte", "anio", "id_mes"}.issubset(cols)

    # Numéricos geográficos (por si hay)
    if "lat" in df.columns: df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    if "lon" in df.columns: df["lon"] = pd.to_numeric(df["lon"], errors="coerce")

    # 🔧 Fix mojibake en TRANSPORTE globalmente (sirve para gráficos/leyendas)
    if "transporte" in df.columns:
        df["transporte"] = df["transporte"].astype(str).apply(_fix_mojibake_text).str.strip()

    # 🔧 Normalización de VARIABLE (solo si existe)
    if "variable" in df.columns:
        df["variable_norm2"] = normalize_variable_series(df["variable"])

    # Asegurar VALOR numérico si existe
    if "valor" in df.columns:
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    df.attrs["schema"] = "B" if has_schema_b else ("A" if has_schema_a else "unknown")
    return df

def get_numeric_columns(df: pd.DataFrame) -> List[str]:
    return df.select_dtypes(include=["number"]).columns.tolist()

def get_categorical_columns(df: pd.DataFrame) -> List[str]:
    return df.select_dtypes(include=["object", "category"]).columns.tolist()

# =============================================================
# Geo helpers (para la pestaña de mapa tradicional)
# =============================================================
def guess_lat_lon(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str], float, float, float, float, float, float]:
    name_lat_candidates = [c for c in df.columns if re.search(r'\b(lat|latitude|latitud|y)\b', str(c), re.I)]
    name_lon_candidates = [c for c in df.columns if re.search(r'\b(lon|lng|long|longitude|longitud|x)\b', str(c), re.I)]

    def validate(col, lo, hi):
        s = pd.to_numeric(df[col], errors="coerce")
        ok = s.between(lo, hi)
        pct = float(ok.mean()) if len(s.dropna()) else 0.0
        return float(s.min(skipna=True) if s.notna().any() else np.nan), \
               float(s.max(skipna=True) if s.notna().any() else np.nan), pct

    for la in name_lat_candidates:
        lat_min, lat_max, pct_lat = validate(la, -90, 90)
        if pct_lat >= 0.7:
            for lo in name_lon_candidates:
                lon_min, lon_max, pct_lon = validate(lo, -180, 180)
                if pct_lon >= 0.7:
                    return la, lo, lat_min, lat_max, lon_min, lon_max, pct_lat, pct_lon

    num_cols = get_numeric_columns(df)
    for la in num_cols:
        lat_min, lat_max, pct_lat = validate(la, -90, 90)
        if pct_lat >= 0.7:
            for lo in num_cols:
                if lo == la: continue
                lon_min, lon_max, pct_lon = validate(lo, -180, 180)
                if pct_lon >= 0.7:
                    return la, lo, lat_min, lat_max, lon_min, lon_max, pct_lat, pct_lon

    return None, None, np.nan, np.nan, np.nan, np.nan, 0.0, 0.0

# =============================================================
# Sidebar – Carga y ajustes
# =============================================================
with st.sidebar:
    st.header("⚙️ Configuración y carga de datos")
    st.subheader("1) Archivo CSV")
    data_file = st.file_uploader(
        "Sube tu CSV (UTF‑8 recomendado)", type=["csv"], key="data_uploader"
    )
    st.caption("Esquema A: VARIABLE/VALOR | Esquema B: AUTOBUSES/PASAJEROS")

    st.subheader("3) Rendimiento para mapa de puntos")
    max_points_map = st.slider("Máx. puntos a renderizar (muestra aleatoria)", 500, 100_000, 10_000, step=500)
    map_mode = st.selectbox("Modo de puntos", ["Marcadores (cluster)", "Heatmap de densidad", "Ambos"], index=0)

if data_file is None:
    st.info("👋 Sube tu archivo **CSV** en la barra lateral para comenzar.")
    st.stop()

# Carga principal
df = load_csv_any(data_file)
schema = df.attrs.get("schema", "unknown")
numeric_cols = get_numeric_columns(df)
categorical_cols = get_categorical_columns(df)

# =============================================================
# 🔁 MONITOREO EN TIEMPO REAL (SIMULADO) — AUTO-RERUN + WATCHER
# =============================================================
with st.sidebar:
    st.subheader("5) Monitoreo en tiempo real (simulado)")
    rt_enabled = st.toggle("Activar simulación (CSV en vivo)", value=False, help="Genera datos de ejemplo cada N segundos")
    rt_interval = st.slider("Intervalo (seg)", 2, 30, 2, help="Frecuencia de generación y refresco")
    rt_window_min = st.slider("Ventana KPI (min)", 1, 60, 10, help="Ventana de agregación para la métrica")
    rt_file = st.text_input("Ruta del CSV de stream", value="stream/pasajeros_stream.csv")

# --- Simulador: CSV en vivo (daemon thread)
def _ensure_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _append_row_atomic(path: str, row: dict):
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    for _ in range(5):
        try:
            pd.DataFrame([row]).to_csv(path, mode="a", index=False, header=write_header, encoding="utf-8")
            break
        except Exception:
            time.sleep(0.05)

def _simulator_worker(path: str, interval: int, stop_event: threading.Event):
    _ensure_dir(path)
    if not os.path.exists(path):
        pd.DataFrame(columns=["ts","transporte","autobuses","pasajeros"]).to_csv(path, index=False, encoding="utf-8")

    rng = np.random.default_rng(seed=42)
    transportes = ["Metrobús", "Transmetro", "Transmetro García-Monterrey-Guadalupe"]
    while not stop_event.is_set():
        t_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        t = random.choice(transportes)
        if t == "Metrobús":
            autobuses = max(0, int(rng.normal(40, 5)))
            pasajeros = max(0, int(rng.normal(200_000, 40_000)))
        elif t == "Transmetro":
            autobuses = max(0, int(rng.normal(260, 25)))
            pasajeros = max(0, int(rng.normal(3_500_000, 300_000)))
        else:
            autobuses = max(0, int(rng.normal(38, 4)))
            pasajeros = max(0, int(rng.normal(800_000, 120_000)))

        row = {"ts": t_now, "transporte": t, "autobuses": autobuses, "pasajeros": pasajeros}
        _append_row_atomic(path, row)
        stop_event.wait(interval)

# Gestión de hilo del simulador
if "rt_thread" not in st.session_state:
    st.session_state["rt_thread"] = None
    st.session_state["rt_stop"] = None
    st.session_state["rt_cfg"] = (None, None)

if rt_enabled:
    cfg = (rt_file, rt_interval)
    if st.session_state["rt_thread"] is None or not st.session_state["rt_thread"].is_alive() or st.session_state["rt_cfg"] != cfg:
        if st.session_state["rt_stop"] is not None:
            st.session_state["rt_stop"].set()
        stop_event = threading.Event()
        th = threading.Thread(target=_simulator_worker, args=(rt_file, rt_interval, stop_event), daemon=True)
        th.start()
        st.session_state["rt_thread"] = th
        st.session_state["rt_stop"] = stop_event
        st.session_state["rt_cfg"] = cfg
else:
    if st.session_state.get("rt_stop"):
        st.session_state["rt_stop"].set()
    st.session_state["rt_stop"] = None
    st.session_state["rt_thread"] = None
    st.session_state["rt_cfg"] = (None, None)

# --- Watcher de mtime del CSV para invalidar la caché al vuelo
if "rt_last_mtime" not in st.session_state:
    st.session_state["rt_last_mtime"] = 0.0

def _get_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0

@st.cache_data(ttl=2, show_spinner=False)  # ttl corto para “verlo moverse”
def load_stream(path: str) -> pd.DataFrame:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=["ts","transporte","autobuses","pasajeros"])
    s = pd.read_csv(path, encoding="utf-8")
    s["ts"] = pd.to_datetime(s["ts"], errors="coerce")
    s = s.dropna(subset=["ts"])
    s["transporte"] = s["transporte"].astype(str).str.strip()
    s["autobuses"] = pd.to_numeric(s["autobuses"], errors="coerce")
    s["pasajeros"] = pd.to_numeric(s["pasajeros"], errors="coerce")
    return s

current_mtime = _get_mtime(rt_file)
if current_mtime != st.session_state["rt_last_mtime"]:
    st.session_state["rt_last_mtime"] = current_mtime
    load_stream.clear()

stream_df = load_stream(rt_file)

# --- Sección visual del monitoreo
st.markdown("## ⏱️ Monitoreo en tiempo real (simulado)")
c1, c2, c3 = st.columns([1,2,1])
with c2:
    st.caption(f"Fuente en vivo: `{rt_file}` — Intervalo: **{rt_interval}s** — Ventana KPI: **{rt_window_min} min**")

now_ts = pd.Timestamp.now()
cut = now_ts - pd.Timedelta(minutes=rt_window_min)
recent = stream_df[stream_df["ts"] >= cut].copy()
prev = stream_df[(stream_df["ts"] < cut) & (stream_df["ts"] >= cut - pd.Timedelta(minutes=rt_window_min))]

kpi_now = int(recent["pasajeros"].sum()) if not recent.empty else 0
kpi_prev = int(prev["pasajeros"].sum()) if not prev.empty else 0
delta = kpi_now - kpi_prev

with c1: st.metric("Pasajeros (ventana actual)", f"{kpi_now:,}", delta=f"{delta:+,}")
with c3: st.metric("Eventos recibidos", f"{len(recent):,}")

allowed = ["Metrobús", "Transmetro", "Transmetro García-Monterrey-Guadalupe"]
recent3 = recent[recent["transporte"].isin(allowed)].copy()
palette_rt = {"Metrobús": BRAND["TERTIARY"], "Transmetro": BRAND["PRIMARY"], "Transmetro García-Monterrey-Guadalupe": BRAND["SECONDARY"]}

if not recent3.empty:
    fig_rt = px.line(
        recent3.sort_values("ts"),
        x="ts", y="pasajeros", color="transporte",
        color_discrete_map=palette_rt, markers=True,
        title="Serie de tiempo (Pasajeros recientes)",
        template=DEFAULT_TEMPLATE
    )
    fig_rt.update_layout(height=380, legend_title="Transporte", xaxis_title="Tiempo", yaxis_title="Pasajeros")
    st.plotly_chart(fig_rt, use_container_width=True)
else:
    st.info("Aún no hay datos en la ventana seleccionada. Activa la simulación o espera al siguiente intervalo.")

st.divider()

# =============================================================
# Filtros (comunes a ambos esquemas)
# =============================================================
st.sidebar.subheader("4) Filtros")
default_metric = "pasajeros" if "pasajeros" in df.columns else ("valor" if "valor" in df.columns else (numeric_cols[0] if numeric_cols else None))
metric = st.sidebar.selectbox(
    "Métrica principal (para agregaciones generales)",
    [default_metric] + [c for c in numeric_cols if c != default_metric] if default_metric else numeric_cols,
    index=0 if default_metric else None,
)
anios = sorted(df["anio"].dropna().unique().tolist()) if "anio" in df.columns else []
sel_anios = st.sidebar.multiselect("Año(s)", anios, default=anios if anios else None)

if "mes_nombre" in df.columns:
    meses_orden = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    presentes = [m for m in meses_orden if m in df["mes_nombre"].dropna().unique()]
    sel_meses = st.sidebar.multiselect("Mes(es)", presentes, default=presentes if presentes else None)
else:
    sel_meses = []

transportes = sorted(df["transporte"].dropna().unique().tolist()) if "transporte" in df.columns else []
sel_transporte = st.sidebar.multiselect("Transporte", transportes)

filtered = df.copy()
if sel_anios:
    filtered = filtered[filtered["anio"].isin(sel_anios)]
if sel_meses and "mes_nombre" in filtered.columns:
    filtered = filtered[filtered["mes_nombre"].isin(sel_meses)]
if sel_transporte:
    filtered = filtered[filtered["transporte"].isin(sel_transporte)]

# Resumen
st.markdown("### 🎯 Resumen")
rc1, rc2, rc3 = st.columns(3)
with rc1: st.metric("Filas totales", f"{len(df):,}")
with rc2: st.metric("Filas filtradas", f"{len(filtered):,}")
with rc3: st.metric("Columnas numéricas", f"{len(numeric_cols)}")
st.divider()

# =============================================================
# Pestañas
# =============================================================
tab_mapa, tab_heatmap, tab_burbujas = st.tabs([
    "🗺️ Mapa de puntos",
    "🔥 Heatmap Mes × Transporte",
    "🫧 Bubble chart (Flota vs Pasajeros)"
])

# =============================================================
# TAB: Mapa (4 puntos fijos AMG + opción coord/centroides)
# =============================================================
with tab_mapa:
    st.subheader("Mapa: 4 puntos fijos (Monterrey/Guadalupe/San Nicolás/Apodaca)")
    fuente = st.radio("Fuente de puntos", ["Puntos fijos (4 municipios AMG)", "Coord. del CSV/centroides"], horizontal=True)

    puntos_fijos = {
        "Monterrey Centro":  dict(lat=25.6866, lon=-100.3161, cvegeo="19039"),
        "Guadalupe":         dict(lat=25.6768, lon=-100.2565, cvegeo="19026"),
        "San Nicolás":       dict(lat=25.7500, lon=-100.3000, cvegeo="19046"),
        "Apodaca":           dict(lat=25.7800, lon=-100.2000, cvegeo="19006"),
    }

    if fuente == "Puntos fijos (4 municipios AMG)":
        valores = {
            "Monterrey Centro": 85175447,
            "Guadalupe": 8862685,
            "Apodaca": 1548897,
            "San Nicolás": 19534705
        }
        heat_data = []
        for nombre, info in puntos_fijos.items():
            lat, lon = info["lat"], info["lon"]
            peso = float(valores.get(nombre, 0.0))
            heat_data.append([lat, lon, peso])

        # === Mapa claro y gradiente visible
        m = folium.Map(location=[25.6866, -100.3161], zoom_start=11, tiles="CartoDB Positron")
        HeatMap(
            data=heat_data, radius=25, blur=22, min_opacity=0.2, max_zoom=18,
            gradient={0.0: "rgba(0,0,255,0.40)", 0.5: "rgba(0,255,255,0.60)",
                      0.8: "rgba(255,255,0,0.70)", 1.0: "rgba(255,0,0,0.90)"}
        ).add_to(m)

        # Marcadores contrastantes en base clara
        for (nombre, info), (_, _, peso) in zip(puntos_fijos.items(), heat_data):
            folium.CircleMarker(
                location=[info["lat"], info["lon"]],
                radius=6,
                color="#1f77b4",
                fill=True,
                fill_color="#1f77b4",
                fill_opacity=0.9,
                tooltip=f"{nombre} | Pasajeros: {int(peso):,}".replace(",", ".")
            ).add_to(m)

        st_folium(m, width="100%", height=630)

    else:
        st.caption("Usando coordenadas del CSV/centroides (vista tradicional).")
        g_lat = next((c for c in filtered.columns if c.lower() in ["lat","latitude","latitud","y"]), None)
        g_lon = next((c for c in filtered.columns if c.lower() in ["lon","lng","long","longitude","longitud","x"]), None)
        all_cols = list(filtered.columns)
        lat_col = st.selectbox("Columna de Latitud", ["(ninguna)"] + all_cols, index=(all_cols.index(g_lat)+1) if g_lat in all_cols else 0)
        lon_col = st.selectbox("Columna de Longitud", ["(ninguna)"] + all_cols, index=(all_cols.index(g_lon)+1) if g_lon in all_cols else 0)

        if lat_col == "(ninguna)" or lon_col == "(ninguna)":
            st.info("Selecciona columnas de latitud y longitud válidas o cambia a 'Puntos fijos'.")
            st.stop()

        pts = filtered.copy()
        pts[lat_col] = pd.to_numeric(pts[lat_col], errors="coerce")
        pts[lon_col] = pd.to_numeric(pts[lon_col], errors="coerce")
        pts = pts.dropna(subset=[lat_col, lon_col])
        if len(pts) == 0:
            st.info("No hay puntos válidos con lat/lon después de filtros.")
            st.stop()

        if len(pts) > max_points_map:
            pts = pts.sample(n=max_points_map, random_state=42)

        lat_c, lon_c = float(pts[lat_col].median()), float(pts[lon_col].median())
        m = folium.Map(location=[lat_c, lon_c], zoom_start=11, tiles="CartoDB Positron")

        if map_mode in ["Marcadores (cluster)", "Ambos"]:
            cluster = MarkerCluster(name="Marcadores").add_to(m)
            tooltip_cols = [c for c in ["transporte", "anio", "mes_nombre", metric] if c in pts.columns]
            for _, r in pts.iterrows():
                tooltip_txt = " | ".join([f"{c}: {r.get(c)}" for c in tooltip_cols])
                folium.CircleMarker(
                    location=[r[lat_col], r[lon_col]],
                    radius=4,
                    color=BRAND["TERTIARY"],
                    fill=True,
                    fill_color=BRAND["TERTIARY"],
                    fill_opacity=0.8,
                    tooltip=tooltip_txt
                ).add_to(cluster)

        if map_mode in ["Heatmap de densidad", "Ambos"]:
            heat_pts = pts[[lat_col, lon_col]].dropna().values.tolist()
            if len(heat_pts) > 0:
                HeatMap(
                    heat_pts, radius=18, blur=15, min_opacity=0.2,
                    gradient={0.0: "rgba(0,0,255,0.35)", 0.5: "rgba(0,255,255,0.55)",
                              0.8: "rgba(255,255,0,0.70)", 1.0: "rgba(255,0,0,0.90)"}
                ).add_to(m)

        st_folium(m, width="100%", height=630)

# =============================================================
# TAB: Heatmap Mes × Transporte (Pasajeros transportados)
# =============================================================
with tab_heatmap:
    st.subheader("Densidad de pasajeros transportados por mes en los diferentes medios de transporte")

    meses_orden = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    id_to_name = {k: v[0] for k, v in SPANISH_MONTHS.items()}

    def _fix_mojibake(s: str) -> str:
        return _fix_mojibake_text(s)  # alias corto

    tmp = filtered.copy()
    if "mes_nombre" not in tmp.columns:
        if "id_mes" in tmp.columns:
            tmp["mes_nombre"] = tmp["id_mes"].astype(str).str.zfill(2).map(id_to_name)
        elif "mes" in tmp.columns:
            tmp["mes_nombre"] = tmp["mes"].astype(str).str.strip().str.capitalize()

    if "transporte" in tmp.columns:
        tmp["transporte"] = tmp["transporte"].astype(str).apply(_fix_mojibake).str.strip()

    if schema == "B":
        req_cols = {"transporte", "mes_nombre", "pasajeros"}
        if not req_cols.issubset(tmp.columns):
            st.info("Tu archivo (Esquema B) debe incluir TRANSPORTE, ID_MES/MES y PASAJEROS para construir el heatmap.")
            st.stop()
        pvt = (tmp.groupby(["transporte", "mes_nombre"], as_index=False)["pasajeros"].sum()
                  .pivot(index="transporte", columns="mes_nombre", values="pasajeros")
                  .reindex(columns=meses_orden).fillna(0))
        colorbar_title = "sum of PASAJEROS"

    elif schema == "A":
        # ✅ Normalización robusta de VARIABLE con mojibake fix
        if "variable_norm2" not in tmp.columns:
            tmp["variable_norm2"] = normalize_variable_series(tmp["variable"])

        req = {"variable_norm2", "valor", "transporte", "mes_nombre"}
        if not req.issubset(tmp.columns):
            st.info("Faltan columnas para el heatmap en Esquema A (se requieren VARIABLE, VALOR, TRANSPORTE y MES).")
            st.stop()

        tmp_pas = tmp[tmp["variable_norm2"] == "pasajeros transportados"].copy()
        pvt = (tmp_pas.groupby(["transporte", "mes_nombre"], as_index=False)["valor"].sum()
                    .pivot(index="transporte", columns="mes_nombre", values="valor")
                    .reindex(columns=meses_orden).fillna(0))
        colorbar_title = "sum of VALOR"
    else:
        st.info("No se reconoce el esquema del archivo.")
        st.stop()

    # Orden sugerido de filas
    orden_filas = [
        "Transmetro García-Monterrey-Guadalupe",
        "Transmetro",
        "Sistema de Transporte Colectivo Metrorrey",
        "Metrobús",
    ]
    presentes = [r for r in orden_filas if r in pvt.index]
    otros = [r for r in pvt.index if r not in presentes]
    pvt = pvt.reindex(presentes + otros)

    fig = px.imshow(
        pvt.values, x=pvt.columns, y=pvt.index,
        color_continuous_scale="Reds", aspect="auto", origin="upper",
        title="Densidad de pasajeros transportados por mes en los diferentes medios de transporte",
        template=DEFAULT_TEMPLATE
    )
    fig.update_layout(
        height=620, margin=dict(l=10, r=10, t=60, b=10),
        coloraxis_colorbar=dict(title=colorbar_title)
    )
    fig.update_xaxes(title="Mes", tickmode="array", tickvals=meses_orden)
    fig.update_yaxes(title="Transporte")
    st.plotly_chart(fig, use_container_width=True)

# =============================================================
# TAB: Bubble chart (Flota vs Pasajeros) — robusto para Esquema A
# =============================================================
with tab_burbujas:
    st.subheader("Relación entre flota y pasajeros transportados")

    orden_transportes = ["Metrobús", "Transmetro", "Transmetro García-Monterrey-Guadalupe"]
    palette = {"Metrobús": BRAND["TERTIARY"], "Transmetro": BRAND["PRIMARY"], "Transmetro García-Monterrey-Guadalupe": BRAND["SECONDARY"]}

    def _fix_mojibake(s: str) -> str:
        return _fix_mojibake_text(s)

    if schema == "B":
        base = filtered.copy()
        if "mes_nombre" not in base.columns and "id_mes" in base.columns:
            base["mes_nombre"] = base["id_mes"].astype(str).str.zfill(2).map({k: v[0] for k, v in SPANISH_MONTHS.items()})
        req = {"anio","id_mes","transporte","autobuses","pasajeros"}
        if not req.issubset(base.columns):
            st.warning("Faltan columnas para el Bubble chart (Esquema B).")
        else:
            base["transporte"] = base["transporte"].astype(str).apply(_fix_mojibake).str.strip()
            df_plot = base[base["transporte"].isin(orden_transportes)].copy()
            presentes = [t for t in orden_transportes if t in df_plot["transporte"].unique()]
            if not presentes:
                presentes = sorted(df_plot["transporte"].unique().tolist())
            df_plot["transporte"] = pd.Categorical(df_plot["transporte"], categories=presentes, ordered=True)

            fig = px.scatter(
                df_plot, x="autobuses", y="pasajeros",
                color="transporte", color_discrete_map=palette,
                category_orders={"transporte": presentes},
                hover_data=["anio","mes_nombre","transporte","autobuses","pasajeros"],
                title="Flota (Autobuses) vs Pasajeros",
                template=DEFAULT_TEMPLATE
            )
            fig.update_layout(xaxis_title="Autobuses en operación (L‑V)",
                              yaxis_title="Pasajeros transportados",
                              height=620, legend_title="TRANSPORTE")
            st.plotly_chart(fig, use_container_width=True)

    elif schema == "A":
        base = filtered.copy()

        # ✅ Normalización robusta en VARIABLE (corrige mojibake) y TRANSPORTE
        if "variable_norm2" not in base.columns:
            base["variable_norm2"] = normalize_variable_series(base.get("variable", pd.Series(dtype=str)))
        base["transporte"] = base.get("transporte", pd.Series(dtype=str)).astype(str).apply(_fix_mojibake).str.strip()

        # Mes legible para hover
        mes_map = {k: v[0] for k, v in SPANISH_MONTHS.items()}
        if "id_mes" in base.columns and "mes_nombre" not in base.columns:
            base["mes_nombre"] = base["id_mes"].astype(str).str.zfill(2).map(mes_map)

        # Variables de interés
        var_autos_lv = "autobuses en operacion de lunes a viernes"
        var_pasaj    = "pasajeros transportados"

        # asegurar numérico
        base["valor"] = pd.to_numeric(base["valor"], errors="coerce")

        # X = Autobuses (L-V) | Y = Pasajeros
        keys = ["anio", "id_mes", "transporte"]
        df_x = (base[base["variable_norm2"] == var_autos_lv]
                .groupby(keys, as_index=False)["valor"].sum()
                .rename(columns={"valor":"AUTOBUSES_LV"}))
        df_y = (base[base["variable_norm2"] == var_pasaj]
                .groupby(keys, as_index=False)["valor"].sum()
                .rename(columns={"valor":"PASAJEROS"}))

        df_merge = pd.merge(df_x, df_y, on=keys, how="inner")
        df_merge["MES"] = df_merge["id_mes"].astype(str).str.zfill(2).map(mes_map)

        # Categorías disponibles (dinámicas)
        candidatos = orden_transportes
        presentes = [t for t in candidatos if t in df_merge["transporte"].unique()]
        if not presentes:
            presentes = sorted(df_merge["transporte"].unique().tolist())
        df_merge["transporte"] = pd.Categorical(df_merge["transporte"], categories=presentes, ordered=True)

        if df_merge.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.info("No hay datos tras combinar las variables seleccionadas.\n\n"
                        "Revisa filtros (Año/Mes/Transporte) o la normalización de VARIABLE.")
            with c2:
                st.caption(f"Filas Autobuses(L‑V): {(base['variable_norm2'] == var_autos_lv).sum():,}")
                st.caption(f"Filas Pasajeros: {(base['variable_norm2'] == var_pasaj).sum():,}")
        else:
            # (Opcional) tamaño de burbuja: intentamos 'Rutas' si existe
            size_col = None
            var_rutas = "rutas"
            try:
                df_s = (base[base["variable_norm2"] == var_rutas]
                        .groupby(keys, as_index=False)["valor"].sum()
                        .rename(columns={"valor":"RUTAS"}))
                df_merge = df_merge.merge(df_s, on=keys, how="left")
                size_col = "RUTAS"
            except Exception:
                size_col = None

            fig = px.scatter(
                df_merge,
                x="AUTOBUSES_LV", y="PASAJEROS",
                color="transporte",
                size=size_col,  # usa tamaño si se calculó
                color_discrete_map=palette,
                category_orders={"transporte": presentes},
                hover_data=["anio","MES","transporte","AUTOBUSES_LV","PASAJEROS"] + ([size_col] if size_col else []),
                title="Relación entre flota (Autobuses L‑V) y pasajeros transportados",
                template=DEFAULT_TEMPLATE
            )
            fig.update_layout(xaxis_title="Autobuses en operación (L‑V)",
                              yaxis_title="Pasajeros transportados",
                              height=620, legend_title="TRANSPORTE")
            # Si lo prefieres, activa escala log para separar nubes:
            # fig.update_yaxes(type="log")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No se reconoce el esquema del archivo. Verifica columnas.")

# =============================================================
# Consejos de rendimiento
# =============================================================
with st.expander("🚀 Sugerencias de rendimiento / Big Data"):
    st.markdown("""
- **Monitoreo**: usa `Intervalo (seg)` bajo (2–5s) y ventana KPI corta (5–10 min) para percibir mejor el “vivo”.
- **Auto-rerun**: esta app usa `st.rerun()` (no recarga el navegador) y watcher por **mtime** para recarga inmediata del CSV.
- **Mapa**: el modo **Heatmap** escala mejor que miles de marcadores; usa muestreo si hay muchos puntos.
- **@st.cache_data** ya se usa con `ttl` corto para el stream y evita recargas innecesarias.
    """)

# =============================================================
# 🔁 Auto-actualización suave al FINAL del script (no recarga página)
# =============================================================
if 'rt_enabled' in locals() and rt_enabled:
    time.sleep(max(1, int(rt_interval)))  # espera el intervalo configurado
    st.rerun()  # re-ejecuta el script conservando el estado (incluye el CSV subido)