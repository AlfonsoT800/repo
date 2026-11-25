"""
Práctica 12 · Tu API
Herramientas de Visualización · Unidad II · UPQ

API elegida: NASA NeoWs (Near Earth Object Web Service), endpoint /neo/rest/v1/feed
Documentación: https://api.nasa.gov  (sección "Asteroids NeoWs")

Cómo usarlo
-----------
1. Consigue tu llave gratis en https://api.nasa.gov (formulario con nombre y correo;
   llega al instante por correo).
2. Guárdala en un archivo token.txt (junto a este script), SOLO la llave, sin comillas,
   o bien en la variable de entorno NASA_API_KEY.
3. python practica12.py              -> consulta la API la primera vez y guarda respuesta.json
                                        las siguientes veces lee el archivo (no gasta peticiones)
   python practica12.py --refrescar -> fuerza una nueva consulta a la API

Salidas: respuesta.json, grafica1..4 (.png), salida_terminal.txt y hallazgos.json
(estos dos últimos los usa armar_reporte.py para armar el reporte).

IMPORTANTE: el token nunca se imprime ni se guarda (ni en pantalla, ni en respuesta.json).
"""

import datetime as dt
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

# ───────────────────────── Configuración ─────────────────────────
AQUI = Path(__file__).resolve().parent
ARCHIVO_TOKEN = AQUI / "token.txt"
VARIABLE_ENTORNO = "NASA_API_KEY"
ARCHIVO_RESPUESTA = AQUI / "respuesta.json"
ARCHIVO_SALIDA = AQUI / "salida_terminal.txt"
ARCHIVO_HALLAZGOS = AQUI / "hallazgos.json"

URL = "https://api.nasa.gov/neo/rest/v1/feed"
FECHA_INICIO = dt.date(2026, 10, 1)   # primer día a consultar
SEMANAS = 4                           # cada petición cubre 7 días (máximo que permite la API)
MINIMO_REGISTROS = 200

# Paleta del curso
GRIS = "#B9C3D1"
AZUL = "#1C4C9A"

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# ───────────────────────── Utilidades ─────────────────────────
class Tee:
    """Duplica lo que se imprime: pantalla + archivo (para pegarlo en el reporte)."""

    def __init__(self, *flujos):
        self.flujos = flujos

    def write(self, texto):
        for f in self.flujos:
            f.write(texto)

    def flush(self):
        for f in self.flujos:
            f.flush()


def salir(mensaje):
    print(f"\n✗ {mensaje}")
    raise SystemExit(1)


def ocultar(texto, token):
    """Quita el token de cualquier texto antes de imprimirlo o guardarlo."""
    return texto.replace(token, "TOKEN_OCULTO") if token else texto


def fecha_corta(f):
    f = pd.Timestamp(f)
    return f"{f.day} {MESES[f.month - 1]}"


def titulo(ax, texto):
    ax.set_title("\n".join(textwrap.wrap(texto, 62)), loc="left", fontsize=13,
                 fontweight="bold", color="#222222")


def estilo(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", color="#E6EAF0", linewidth=0.8)
    ax.set_axisbelow(True)


# ───────────────────────── 1. Token ─────────────────────────
def leer_token():
    """Lee el token desde fuera del código y lo valida. Si no sirve, se detiene."""
    token = os.environ.get(VARIABLE_ENTORNO, "").strip()
    origen = f"la variable de entorno {VARIABLE_ENTORNO}"
    if not token and ARCHIVO_TOKEN.exists():
        token = ARCHIVO_TOKEN.read_text(encoding="utf-8").strip()
        origen = "token.txt"

    if not token:
        salir("No encontré el token. Guárdalo en token.txt (junto al script) o en la "
              f"variable de entorno {VARIABLE_ENTORNO}. Se consigue gratis en https://api.nasa.gov")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,}", token):
        salir(f"El token que leí de {origen} no tiene formato válido (debe tener al menos 8 "
              "caracteres, sin espacios ni saltos de línea). ¿Lo copiaste completo?")
    if token == "DEMO_KEY":
        print("! Estás usando DEMO_KEY: sirve para probar, pero solo permite ~30 peticiones por hora "
              "y 50 por día. Pide tu llave personal en https://api.nasa.gov")
    print(f"✓ Token leído de {origen} ({len(token)} caracteres, no se muestra).")
    return token


# ───────────────────────── 2-3. Petición con validaciones ─────────────────────────
def pedir_semana(token, inicio, fin):
    parametros = {"start_date": inicio.isoformat(), "end_date": fin.isoformat(), "api_key": token}
    try:
        r = requests.get(URL, params=parametros, timeout=30)
    except requests.exceptions.RequestException as e:
        # No se imprime el mensaje de la excepción: incluye la URL completa con el token.
        salir(f"No se pudo conectar con la API ({type(e).__name__}). Revisa tu internet. "
              "Si ya tienes respuesta.json, bórralo solo si quieres volver a consultar.")

    codigo = r.status_code
    if codigo in (401, 403):
        salir(f"Error {codigo}: la API rechazó el token. Está mal copiado, vencido o es inválido. "
              "Revisa token.txt.")
    if codigo == 400:
        salir("Error 400: la petición está mal hecha (fechas inválidas o rango mayor a 7 días). "
              f"Detalle del servidor: {ocultar(r.text[:200], token)}")
    if codigo == 429:
        salir("Error 429: te pasaste del límite de peticiones. Espera un rato (el límite se "
              "renueva por hora) o usa tu llave personal en lugar de DEMO_KEY.")
    if codigo >= 500:
        salir(f"Error {codigo}: falla del servidor de la NASA, no tuya. Intenta más tarde.")
    if codigo != 200:
        salir(f"Código de estado inesperado: {codigo}. {ocultar(r.text[:200], token)}")

    # Un 200 no garantiza JSON: puede ser una página de error.
    if "json" not in (r.headers.get("Content-Type") or ""):
        print(ocultar(r.text[:300], token))
        raise SystemExit(1)

    restantes = r.headers.get("X-RateLimit-Remaining")
    if restantes is not None:
        print(f"  Peticiones restantes en tu límite: {restantes}")
    return r.json()


def consultar_api():
    token = leer_token()
    combinado = {"near_earth_objects": {}, "element_count": 0,
                 "consulta": {"inicio": FECHA_INICIO.isoformat(), "semanas": SEMANAS}}
    for i in range(SEMANAS):
        inicio = FECHA_INICIO + dt.timedelta(days=7 * i)
        fin = inicio + dt.timedelta(days=6)
        print(f"→ Consultando {inicio} a {fin} ...")
        datos = pedir_semana(token, inicio, fin)
        if "near_earth_objects" not in datos:
            salir("El JSON llegó, pero no trae la llave 'near_earth_objects'. ¿Cambió la API?")
        combinado["near_earth_objects"].update(datos["near_earth_objects"])
        combinado["element_count"] += datos.get("element_count", 0)
        time.sleep(1)  # cortesía con el servidor

    # Guardar la respuesta SIN token (las URLs "links" que devuelve la NASA lo traen).
    texto = ocultar(json.dumps(combinado, ensure_ascii=False, indent=1), token)
    assert token not in texto
    ARCHIVO_RESPUESTA.write_text(texto, encoding="utf-8")
    print(f"✓ Respuesta guardada en {ARCHIVO_RESPUESTA.name} ({len(texto) / 1024:.0f} KB).")
    return combinado


def obtener_datos(refrescar):
    if ARCHIVO_RESPUESTA.exists() and not refrescar:
        print(f"✓ Leyendo {ARCHIVO_RESPUESTA.name} (sin gastar peticiones).")
        try:
            datos = json.loads(ARCHIVO_RESPUESTA.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            salir(f"{ARCHIVO_RESPUESTA.name} está dañado. Bórralo y vuelve a ejecutar.")
        if "near_earth_objects" not in datos:
            salir(f"{ARCHIVO_RESPUESTA.name} no tiene la llave 'near_earth_objects'.")
        return datos
    return consultar_api()


# ───────────────────────── 4-5. Tabla y limpieza ─────────────────────────
def aplanar(datos):
    """datos['near_earth_objects'][fecha] = lista de asteroides  ->  una fila por asteroide."""
    filas = []
    for fecha, lista in datos["near_earth_objects"].items():
        for o in lista:
            pasos = o.get("close_approach_data") or []
            paso = next((p for p in pasos if p.get("close_approach_date") == fecha),
                        pasos[0] if pasos else {})
            metros = (o.get("estimated_diameter") or {}).get("meters") or {}
            filas.append({
                "id": o.get("id"),
                "nombre": o.get("name"),
                "fecha": fecha,
                "magnitud_h": o.get("absolute_magnitude_h"),
                "diametro_min_m": metros.get("estimated_diameter_min"),
                "diametro_max_m": metros.get("estimated_diameter_max"),
                "velocidad_kms": (paso.get("relative_velocity") or {}).get("kilometers_per_second"),
                "distancia_lunar": (paso.get("miss_distance") or {}).get("lunar"),
                "peligroso": o.get("is_potentially_hazardous_asteroid"),
            })
    return pd.DataFrame(filas)


def limpiar(df):
    print("\n══════ LIMPIEZA DE DATOS ══════")
    print(f"Registros al cargar: {len(df)}")
    print("\nTipos de dato al cargar:")
    print(df.dtypes.to_string())
    print("\nFaltantes por columna:")
    print(df.isna().sum().to_string())

    # Algunas columnas numéricas llegan como texto en el JSON: se convierten.
    print("\nConversión de texto a número:")
    for col in ["magnitud_h", "diametro_min_m", "diametro_max_m", "velocidad_kms", "distancia_lunar"]:
        antes = df[col].isna().sum()
        era_texto = df[col].map(lambda v: isinstance(v, str)).sum()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        perdidos = df[col].isna().sum() - antes
        print(f"  {col:16s} texto: {era_texto:4d} | perdidos al convertir: {perdidos}")

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["peligroso"] = df["peligroso"].fillna(False).astype(bool)

    n0 = len(df)
    df = df.drop_duplicates(subset=["id", "fecha"])
    print(f"\nDuplicados eliminados: {n0 - len(df)}")

    n1 = len(df)
    df = df.dropna(subset=["fecha", "diametro_max_m", "velocidad_kms", "distancia_lunar", "magnitud_h"])
    print(f"Eliminados por faltantes en columnas clave: {n1 - len(df)}")

    n2 = len(df)
    df = df[(df["diametro_max_m"] > 0) & (df["velocidad_kms"] > 0) & (df["distancia_lunar"] > 0)]
    print(f"Eliminados por valores no positivos (escala log): {n2 - len(df)}")

    df = df.reset_index(drop=True)
    print(f"\n✓ Registros utilizables: {len(df)}")
    if len(df) < MINIMO_REGISTROS:
        print(f"! Hay menos de {MINIMO_REGISTROS} registros: sube SEMANAS en la configuración "
              "y ejecuta con --refrescar.")

    df["tamano"] = pd.cut(df["diametro_max_m"], bins=[0, 50, 140, np.inf],
                          labels=["Pequeño", "Mediano", "Grande"])
    print("\nResumen numérico:")
    print(df[["diametro_max_m", "velocidad_kms", "distancia_lunar", "magnitud_h"]]
          .describe().round(2).to_string())
    return df


# ───────────────────────── Gráficas ─────────────────────────
def grafica_distribucion(df):
    d = df["diametro_max_m"]
    pct_peq = (d < 50).mean() * 100
    n_gr = int((d > 140).sum())
    pregunta = "¿Cómo se reparten los tamaños de los asteroides que pasan cerca de la Tierra y hay casos extremos?"
    tit = (f"{pct_peq:.0f}% de los asteroides mide menos de 50 m; "
           f"solo {n_gr} superan los 140 m")

    fig, ax = plt.subplots(figsize=(8, 5))
    bordes = np.logspace(np.log10(d.min()), np.log10(d.max()), 31)
    _, b, parches = ax.hist(d, bins=bordes, color=GRIS, edgecolor="white")
    for p, izq in zip(parches, b[:-1]):
        if izq >= 140:
            p.set_facecolor(AZUL)
    ax.set_xscale("log")
    ax.axvline(140, color="#555555", linestyle="--", linewidth=1)
    ax.text(140, ax.get_ylim()[1] * 0.95, " 140 m", color="#555555", va="top", fontsize=9)
    ax.set_xlabel("Diámetro máximo estimado (m, escala logarítmica)")
    ax.set_ylabel("Número de asteroides")
    titulo(ax, tit)
    estilo(ax)
    fig.savefig(AQUI / "grafica1_distribucion.png", dpi=200, bbox_inches="tight")

    mayor = df.loc[d.idxmax()]
    lectura = (f"La mediana del diámetro máximo estimado es {d.median():.0f} m, pero el más grande "
               f"({mayor['nombre']}) llega a {d.max():.0f} m: un caso extremo muy por encima del resto. "
               "La cola larga hacia la derecha obliga a usar escala logarítmica. Una posible lectura: "
               "hay muchos más cuerpos pequeños que grandes, y los pequeños solo se detectan cuando "
               "pasan relativamente cerca, así que esta muestra no es un censo completo del cielo.")
    return {"titulo": tit, "pregunta": pregunta, "lectura": lectura,
            "archivo": "grafica1_distribucion.png", "tipo": "Distribución"}


def grafica_comparacion(df):
    grupos = [g for g in ["Pequeño", "Mediano", "Grande"] if (df["tamano"] == g).any()]
    datos = [df.loc[df["tamano"] == g, "velocidad_kms"] for g in grupos]
    medianas = [x.median() for x in datos]
    imax, imin = int(np.argmax(medianas)), int(np.argmin(medianas))
    pregunta = "¿Los asteroides grandes se mueven distinto (más rápido o más lento) que los pequeños?"
    if medianas[imax] - medianas[imin] < 1:
        tit = (f"La velocidad mediana casi no cambia con el tamaño: "
               f"de {medianas[imin]:.1f} a {medianas[imax]:.1f} km/s")
    else:
        tit = (f"Los asteroides {grupos[imax].lower()}s son los más rápidos: mediana de "
               f"{medianas[imax]:.1f} km/s frente a {medianas[imin]:.1f} km/s en los {grupos[imin].lower()}s")

    fig, ax = plt.subplots(figsize=(8, 5))
    bp = ax.boxplot(datos, patch_artist=True, widths=0.55,
                    medianprops=dict(color="black", linewidth=1.5),
                    flierprops=dict(marker="o", markersize=3, markerfacecolor="#888888",
                                    markeredgecolor="none", alpha=0.6))
    for i, caja in enumerate(bp["boxes"]):
        caja.set_facecolor(AZUL if i == imax else GRIS)
        caja.set_edgecolor("#555555")
    ax.set_xticks(range(1, len(grupos) + 1))
    ax.set_xticklabels([f"{g}\n(n = {len(x)})" for g, x in zip(grupos, datos)])
    ax.set_xlabel("Tamaño (pequeño < 50 m · mediano 50–140 m · grande > 140 m; diámetro máximo estimado)")
    ax.set_ylabel("Velocidad relativa (km/s)")
    titulo(ax, tit)
    estilo(ax)
    fig.savefig(AQUI / "grafica2_comparacion.png", dpi=200, bbox_inches="tight")

    # ¿Las cajas (50 % central) se traslapan?
    rangos = [(x.quantile(0.25), x.quantile(0.75)) for x in datos]
    separadas = any(a[1] < b[0] or b[1] < a[0]
                    for i, a in enumerate(rangos) for b in rangos[i + 1:])
    cautela = ""
    if min(len(x) for x in datos) < 15:
        cautela = (f" El grupo con menos objetos tiene solo {min(len(x) for x in datos)}, "
                   "así que su mediana debe leerse con cautela.")
    lectura = (f"La velocidad mediana va de {medianas[imin]:.1f} km/s ({grupos[imin].lower()}s) a "
               f"{medianas[imax]:.1f} km/s ({grupos[imax].lower()}s)." + cautela +
               (" Las cajas (el 50 % central de cada grupo) no se traslapan, así que el tamaño sí marca una diferencia."
                if separadas else
                " Las cajas (el 50 % central de cada grupo) se traslapan, así que el tamaño por sí solo no explica la velocidad."))
    return {"titulo": tit, "pregunta": pregunta, "lectura": lectura,
            "archivo": "grafica2_comparacion.png", "tipo": "Comparación"}


def grafica_relacion(df):
    rho = df["velocidad_kms"].rank().corr(df["distancia_lunar"].rank())   # Spearman
    pregunta = "¿Los asteroides más rápidos pasan más lejos o más cerca de la Tierra?"
    if abs(rho) < 0.2:
        tit = f"La velocidad y la distancia de paso casi no se relacionan (ρ\u00a0=\u00a0{rho:.2f})"
        lectura_rho = "prácticamente no se mueven juntas"
    else:
        fuerza = "Hay una tendencia clara" if abs(rho) >= 0.5 else "Hay una ligera tendencia"
        sentido = "pasar más lejos" if rho > 0 else "pasar más cerca"
        tit = f"{fuerza}: los asteroides más rápidos suelen {sentido} (ρ\u00a0=\u00a0{rho:.2f})"
        lectura_rho = f"los más rápidos suelen {sentido}"

    fig, ax = plt.subplots(figsize=(8, 5))
    resto, peli = df[~df["peligroso"]], df[df["peligroso"]]
    ax.scatter(resto["velocidad_kms"], resto["distancia_lunar"], s=18, color=GRIS,
               alpha=0.8, label="Resto")
    if len(peli):
        ax.scatter(peli["velocidad_kms"], peli["distancia_lunar"], s=26, color=AZUL,
                   label="Potencialmente peligroso (según NASA)", zorder=3)
    ax.set_yscale("log")
    ax.set_xlabel("Velocidad relativa (km/s)")
    ax.set_ylabel("Distancia mínima de paso (distancias lunares, escala log)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17),
              ncol=2, markerscale=1.6)
    titulo(ax, tit)
    estilo(ax)
    fig.savefig(AQUI / "grafica3_relacion.png", dpi=200, bbox_inches="tight")

    extra = ""
    if len(peli):
        extra = (f" Los {len(peli)} objetos que la NASA marca como potencialmente peligrosos (azul) pasan a una "
                 f"distancia mediana de {peli['distancia_lunar'].median():.1f} distancias lunares, frente a "
                 f"{resto['distancia_lunar'].median():.1f} del resto.")
    lectura = (f"El coeficiente de Spearman es {rho:.2f}: {lectura_rho}." + extra +
               " Esto es correlación, no causa: la velocidad relativa depende de la órbita del asteroide "
               "y la distancia de paso, de la geometría de cada encuentro.")
    return {"titulo": tit, "pregunta": pregunta, "lectura": lectura,
            "archivo": "grafica3_relacion.png", "tipo": "Relación"}


def grafica_evolucion(df):
    por_dia = df.groupby("fecha").size()
    por_dia = por_dia.reindex(pd.date_range(por_dia.index.min(), por_dia.index.max()), fill_value=0)
    pico = por_dia.idxmax()
    pregunta = "¿Cómo cambió día con día el número de asteroides que pasaron cerca de la Tierra?"
    tit = (f"Los acercamientos varían de {por_dia.min()} a {por_dia.max()} asteroides por día; "
           f"el pico fue el {fecha_corta(pico)}")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(por_dia.index, por_dia.values, color=GRIS, linewidth=2, marker="o", markersize=4)
    ax.plot([pico], [por_dia[pico]], marker="o", markersize=9, color=AZUL, zorder=3)
    ax.annotate(f"{por_dia[pico]} el {fecha_corta(pico)}", (pico, por_dia[pico]),
                textcoords="offset points", xytext=(8, 6), color=AZUL, fontsize=10, fontweight="bold")
    ax.set_ylim(0, por_dia.max() * 1.2)
    ticks = por_dia.index[::3]
    ax.set_xticks(ticks)
    ax.set_xticklabels([fecha_corta(t) for t in ticks], rotation=45, ha="right")
    ax.set_xlabel("Fecha del máximo acercamiento (2026)")
    ax.set_ylabel("Asteroides por día (cantidad)")
    titulo(ax, tit)
    estilo(ax)
    fig.savefig(AQUI / "grafica4_evolucion.png", dpi=200, bbox_inches="tight")

    lectura = (f"En promedio pasaron {por_dia.mean():.1f} asteroides por día; el día pico ({fecha_corta(pico)}) "
               f"tuvo {por_dia.max()} y el más tranquilo {por_dia.min()}. Con solo {len(por_dia)} días no se "
               "puede hablar de una tendencia ni de estacionalidad: la variación diaria puede deberse a las "
               "condiciones de observación y al ritmo de descubrimiento, y no necesariamente a que ese día "
               "«pasen más» objetos.")
    return {"titulo": tit, "pregunta": pregunta, "lectura": lectura,
            "archivo": "grafica4_evolucion.png", "tipo": "Evolución"}


# ───────────────────────── Programa principal ─────────────────────────
def main():
    pd.set_option("display.width", 100)
    datos = obtener_datos(refrescar="--refrescar" in sys.argv)
    df = limpiar(aplanar(datos))
    if df.empty:
        salir("No quedó ningún registro utilizable después de limpiar.")

    print("\n══════ GRÁFICAS ══════")
    hallazgos = [grafica_distribucion(df), grafica_comparacion(df),
                 grafica_relacion(df), grafica_evolucion(df)]
    for h in hallazgos:
        print(f"✓ {h['archivo']}: {h['titulo']}")
    ARCHIVO_HALLAZGOS.write_text(json.dumps(hallazgos, ensure_ascii=False, indent=1), encoding="utf-8")

    plt.show()   # siempre después de savefig, para no guardar imágenes en blanco


if __name__ == "__main__":
    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as log:
        sys.stdout = Tee(sys.__stdout__, log)
        try:
            main()
        finally:
            sys.stdout = sys.__stdout__
