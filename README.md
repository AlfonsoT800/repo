# ☄️ Asteroides cercanos a la Tierra · Dashboard con la API NASA NeoWs

Práctica 12 · Herramientas de Visualización · Universidad Politécnica de Querétaro.

Consume la API **NASA NeoWs** con token, valida la respuesta, limpia los datos y los muestra en un
dashboard interactivo de **Streamlit** con cuatro gráficas (distribución, comparación, relación y evolución).

## Archivos
| Archivo | Para qué sirve |
|---|---|
| `app.py` | Dashboard en Streamlit |
| `practica12.py` | Consulta la API (token, códigos de estado, JSON), guarda `respuesta.json` y limpia los datos |
| `respuesta.json` | Respuesta guardada de la API (sin token) para no gastar peticiones |
| `requirements.txt` | Librerías necesarias |

## Cómo correrlo
1. Consigue una llave gratis en <https://api.nasa.gov>.
2. Instala las librerías: `pip install -r requirements.txt`
3. Guarda tu llave **sola** en un archivo `token.txt` (o en la variable de entorno `NASA_API_KEY`).
4. `python practica12.py` consulta la API la primera vez y crea `respuesta.json`.
5. `streamlit run app.py` abre el dashboard.

## Seguridad
El token **no está en este repositorio**: `token.txt` y `.streamlit/secrets.toml` están en `.gitignore`.
En Streamlit Cloud se configura en *Settings → Secrets* con `NASA_API_KEY = "tu_llave"`.

## Datos
NASA NeoWs, endpoint `/neo/rest/v1/feed`, del 1 al 28 de octubre de 2026 (4 peticiones de 7 días).
