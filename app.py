"""
Dashboard en Streamlit · Asteroides cercanos a la Tierra (NASA NeoWs)

Reutiliza practica12.py (consulta, validación y limpieza) y muestra cuatro gráficas
interactivas con filtros. El token NUNCA va en el código:
  · En tu PC:            archivo token.txt  o variable de entorno NASA_API_KEY
  · En Streamlit Cloud:  App settings → Secrets →  NASA_API_KEY = "tu_llave"

Ejecutar:  streamlit run app.py
"""
import contextlib
import io
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import practica12 as p

GRIS, AZUL = p.GRIS, p.AZUL
st.set_page_config(page_title="Asteroides cercanos a la Tierra", page_icon="☄️", layout="wide")


# ───────────── Datos ─────────────
def token_desde_secretos():
    """En Streamlit Cloud el token vive en Secrets; se pasa por variable de entorno."""
    try:
        valor = st.secrets.get("NASA_API_KEY", "")
    except Exception:
        valor = ""
    if valor:
        os.environ["NASA_API_KEY"] = valor


@st.cache_data(show_spinner="Cargando datos…")
def cargar():
    token_desde_secretos()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            datos = p.obtener_datos(refrescar=False)
            df = p.limpiar(p.aplanar(datos))
    except SystemExit:
        # Los errores no se guardan en caché: al arreglar el token se puede reintentar.
        raise RuntimeError(buf.getvalue().strip().splitlines()[-1])
    return df, buf.getvalue()


try:
    df_total, log_limpieza = cargar()
except RuntimeError as e:
    st.error(f"No se pudieron cargar los datos. {e}")
    st.info("Pon tu llave en token.txt (local) o en Secrets (Streamlit Cloud) y recarga la página.")
    st.stop()

# ───────────── Barra lateral: filtros ─────────────
st.sidebar.header("Filtros")
f_min, f_max = df_total["fecha"].min().date(), df_total["fecha"].max().date()
rango = st.sidebar.date_input("Fechas", (f_min, f_max), min_value=f_min, max_value=f_max)
tamanos = st.sidebar.multiselect("Tamaño", ["Pequeño", "Mediano", "Grande"],
                                 default=["Pequeño", "Mediano", "Grande"],
                                 help="Pequeño < 50 m · Mediano 50–140 m · Grande > 140 m")
solo_peligrosos = st.sidebar.checkbox("Solo potencialmente peligrosos (según NASA)")

if st.sidebar.button("Actualizar desde la API"):
    token_desde_secretos()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            p.consultar_api()
        cargar.clear()
        st.rerun()
    except SystemExit:
        st.sidebar.error(buf.getvalue().strip().splitlines()[-1])

if isinstance(rango, tuple) and len(rango) == 2:
    ini, fin = rango
else:
    ini, fin = f_min, f_max

df = df_total[(df_total["fecha"].dt.date >= ini) & (df_total["fecha"].dt.date <= fin)
              & (df_total["tamano"].isin(tamanos))]
if solo_peligrosos:
    df = df[df["peligroso"]]
if df.empty:
    st.warning("Con estos filtros no queda ningún asteroide. Cambia los filtros.")
    st.stop()


def base(fig, titulo, x, y):
    fig.update_layout(title=dict(text=titulo, x=0, font=dict(size=16)), xaxis_title=x, yaxis_title=y,
                      plot_bgcolor="white", margin=dict(t=70, b=40), font=dict(size=13))
    fig.update_yaxes(gridcolor="#E6EAF0")
    return fig


# ───────────── Encabezado y KPIs ─────────────
st.title("☄️ Asteroides cercanos a la Tierra")
st.caption(f"Datos de la API NASA NeoWs · {p.fecha_corta(ini)} a "
           f"{p.fecha_corta(fin)} de 2026 · {len(df)} asteroides con los filtros actuales")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Asteroides", f"{len(df):,}")
c2.metric("Diámetro mediano", f"{df['diametro_max_m'].median():.0f} m")
c3.metric("Velocidad mediana", f"{df['velocidad_kms'].median():.1f} km/s")
c4.metric("Potencialmente peligrosos", f"{int(df['peligroso'].sum())}")

t1, t2, t3, t4 = st.tabs(["Distribución", "Comparación", "Relación", "Evolución"])

# 1. Distribución
with t1:
    d = df["diametro_max_m"]
    bordes = np.logspace(np.log10(d.min()), np.log10(d.max() * 1.0001), 31)
    conteo, _ = np.histogram(d, bins=bordes)
    colores = [AZUL if izq >= 140 else GRIS for izq in bordes[:-1]]
    fig = go.Figure(go.Bar(x=(bordes[:-1] + bordes[1:]) / 2, y=conteo, width=np.diff(bordes),
                           marker_color=colores, hovertemplate="%{x:.0f} m: %{y} asteroides<extra></extra>"))
    fig.add_vline(x=140, line_dash="dash", line_color="#555", annotation_text="140 m")
    fig.update_xaxes(type="log")
    base(fig, f"{(d < 50).mean() * 100:.0f}% de los asteroides mide menos de 50 m; "
              f"solo {int((d > 140).sum())} superan los 140 m",
         "Diámetro máximo estimado (m, escala logarítmica)", "Número de asteroides")
    st.plotly_chart(fig, width="stretch")
    mayor = df.loc[d.idxmax()]
    st.caption(f"El más grande es {mayor['nombre']}, con {d.max():.0f} m. Los pequeños solo se detectan "
               "cuando pasan cerca, así que la muestra no es un censo completo del cielo.")

# 2. Comparación
with t2:
    grupos = [g for g in ["Pequeño", "Mediano", "Grande"] if (df["tamano"] == g).any()]
    med = df.groupby("tamano", observed=True)["velocidad_kms"].median()
    gmax, gmin = med.idxmax(), med.idxmin()
    if med.max() - med.min() < 1:
        tit = f"La velocidad mediana casi no cambia con el tamaño: de {med.min():.1f} a {med.max():.1f} km/s"
    else:
        tit = (f"Los asteroides {str(gmax).lower()}s son los más rápidos: mediana de {med.max():.1f} km/s "
               f"frente a {med.min():.1f} km/s en los {str(gmin).lower()}s")
    fig = px.box(df, x="tamano", y="velocidad_kms", color="tamano", category_orders={"tamano": grupos},
                 color_discrete_map={g: (AZUL if g == gmax else GRIS) for g in grupos})
    fig.update_layout(showlegend=False)
    base(fig, tit, "Tamaño (pequeño < 50 m · mediano 50–140 m · grande > 140 m)", "Velocidad relativa (km/s)")
    st.plotly_chart(fig, width="stretch")
    st.caption("Si las cajas (50 % central de cada grupo) se traslapan, el tamaño por sí solo no explica la velocidad.")

# 3. Relación
with t3:
    rho = df["velocidad_kms"].rank().corr(df["distancia_lunar"].rank()) if len(df) > 2 else float("nan")
    if np.isnan(rho) or abs(rho) < 0.2:
        tit = f"La velocidad y la distancia de paso casi no se relacionan (ρ = {rho:.2f})"
    else:
        fuerza = "Hay una tendencia clara" if abs(rho) >= 0.5 else "Hay una ligera tendencia"
        sentido = "pasar más lejos" if rho > 0 else "pasar más cerca"
        tit = f"{fuerza}: los asteroides más rápidos suelen {sentido} (ρ = {rho:.2f})"
    df_r = df.assign(clase=np.where(df["peligroso"], "Potencialmente peligroso (NASA)", "Resto"))
    fig = px.scatter(df_r, x="velocidad_kms", y="distancia_lunar", color="clase", log_y=True,
                     color_discrete_map={"Resto": GRIS, "Potencialmente peligroso (NASA)": AZUL},
                     hover_data={"nombre": True, "diametro_max_m": ":.0f"},
                     category_orders={"clase": ["Resto", "Potencialmente peligroso (NASA)"]})
    fig.update_layout(legend=dict(orientation="h", y=-0.2, title=None))
    base(fig, tit, "Velocidad relativa (km/s)", "Distancia mínima de paso (distancias lunares, escala log)")
    st.plotly_chart(fig, width="stretch")
    st.caption("1 distancia lunar ≈ 384,400 km. Correlación no implica causa: la velocidad depende de la "
               "órbita y la distancia, de la geometría de cada encuentro.")

# 4. Evolución
with t4:
    por_dia = df.groupby("fecha").size()
    por_dia = por_dia.reindex(pd.date_range(por_dia.index.min(), por_dia.index.max()), fill_value=0)
    pico = por_dia.idxmax()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=por_dia.index, y=por_dia.values, mode="lines+markers",
                             line=dict(color=GRIS, width=3), marker=dict(color=GRIS, size=7),
                             hovertemplate="%{x|%d/%m}: %{y} asteroides<extra></extra>"))
    fig.add_trace(go.Scatter(x=[pico], y=[por_dia[pico]], mode="markers+text", marker=dict(color=AZUL, size=14),
                             text=[f"{por_dia[pico]} el {p.fecha_corta(pico)}"], textposition="top right",
                             textfont=dict(color=AZUL), hoverinfo="skip"))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(rangemode="tozero")
    base(fig, f"Los acercamientos varían de {por_dia.min()} a {por_dia.max()} asteroides por día; "
              f"el pico fue el {p.fecha_corta(pico)}",
         "Fecha del máximo acercamiento (2026)", "Asteroides por día (cantidad)")
    st.plotly_chart(fig, width="stretch")
    st.caption("Con pocos días no se puede hablar de tendencia; la variación puede deberse a las condiciones "
               "de observación y al ritmo de descubrimiento.")

# ───────────── Datos y limpieza ─────────────
with st.expander("Limpieza de datos (salida del programa)"):
    st.code(log_limpieza)
with st.expander("Ver tabla y descargar"):
    st.dataframe(df.drop(columns=["tamano"]).assign(tamano=df["tamano"].astype(str)), width="stretch")
    st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8"), "asteroides.csv", "text/csv")
