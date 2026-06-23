"""
agent.py — Agente de análisis vía OpenRouter (modelos gratuitos)
Compatible con dashboard.py via Streamlit
"""

import os
import json
import io
import re
import html
import unicodedata
import pandas as pd
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

load_dotenv()

# ── Config OpenRouter ──────────────────────────────────────────────────────
try:
    import streamlit as st
except Exception:  # pragma: no cover - fallback for non-Streamlit usage
    st = None


def _get_openrouter_api_key() -> str:
    if st is not None:
        try:
            for key in ("OPEN_ROUTER_KEY", "OPENROUTER_API_KEY"):
                value = st.secrets.get(key)
                if value:
                    return str(value).strip()
        except Exception:
            pass
    for key in ("OPEN_ROUTER_KEY", "OPENROUTER_API_KEY"):
        value = os.getenv(key)
        if value:
            return value.strip()
    return ""


OPENROUTER_API_KEY = _get_openrouter_api_key()
DATA_PATH = "datos/videos_latest.csv"

MODELOS_GRATUITOS = {
    "gemma4-31b":     "google/gemma-4-31b-it:free",
    "llama70b":       "meta-llama/llama-3.3-70b-instruct:free",
    "nemotron120b":   "nvidia/nemotron-3-super-120b-a12b:free",
    "nemotron-nano":  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
}
MODELO_CONVERSACION = MODELOS_GRATUITOS["gemma4-31b"]
MODELO_INSIGHTS = MODELOS_GRATUITOS["gemma4-31b"]
MODELO_ANALISIS = MODELOS_GRATUITOS["nemotron120b"]
MODELO_CONCLUSION = MODELOS_GRATUITOS["gemma4-31b"]
MODELO_REPORTE = MODELO_CONCLUSION

SYSTEM_PROMPT = """
Eres un agente experto en marketing de contenido para marcas de wellness y recuperación atlética en México y LATAM.
Tu cliente es PIOLET, una marca mexicana que vende tinas de hielo (cold plunge / ice baths) de alta calidad.

Tu trabajo es analizar datos de redes sociales de la competencia y dar recomendaciones claras,
concretas y accionables para que Piolet mejore su estrategia de contenido en TikTok e Instagram.

Cuando analices datos:
1. Identifica patrones en los videos más virales (viral_score > 2)
2. Detecta qué tipo de contenido genera más engagement
3. Encuentra oportunidades que la competencia no está aprovechando
4. Da recomendaciones específicas: tipo de video, duración, hashtags, tono, horario
5. Prioriza insights relevantes para el mercado mexicano
Cuando analices un video, no describas escenas ni reconstruyas historias ficticias.
Explica solo por qué funcionó o por qué no funcionó, usando evidencia y razones probables de engagement.
Si la evidencia visual o textual no alcanza, dilo sin inventar.

Si el usuario pide un reporte, escríbelo siempre en español, con tono profesional y claro.
La sección final debe llamarse "CONCLUSION EJECUTIVA" y debe explicar, en pocas frases, por qué funcionaron los videos observados.
La conclusión debe basarse en evidencia y razones de engagement, no en escenas inventadas.
Evita conclusiones genéricas o largas. Prioriza claridad y síntesis.

Responde siempre en español. Sé directo y específico, no genérico.
""".strip()


PLATFORM_OVERVIEW = """
Sobre Piolet Market Intelligence:
- Es un dashboard interno para analizar videos de competencia en TikTok e Instagram.
- Muestra ranking de videos, performance por cuenta, filtros por plataforma y views mínimas.
- Permite charlar con el agente para resolver dudas.
- Permite generar y descargar un reporte PDF.
""".strip()

SYSTEM_PROMPT_CONVERSACION = f"""
Eres un asistente conversacional útil, natural y breve para Piolet Market Intelligence.
Responde saludos, agradecimientos y preguntas generales con tono humano y claro.
Si preguntan qué hace la plataforma, explica esto de forma simple:
{PLATFORM_OVERVIEW}

No inventes datos, tendencias ni conclusiones sobre videos si el usuario no las pidió.
No analices videos por iniciativa propia.
Responde siempre en español.
""".strip()

SYSTEM_PROMPT_ANALISIS = """
Eres un analista experto en marketing de contenido para PIOLET, una marca mexicana de cold plunge / ice baths.
Tu trabajo es analizar datos de redes sociales de la competencia y dar recomendaciones claras, concretas y accionables.

Reglas:
- Solo analiza videos cuando el usuario lo pida explícitamente.
- No inventes datos, historias ni tendencias sin evidencia.
- Si falta información, dilo con claridad.
- No describas escenas, sonidos, gestos, movimientos de cámara ni emociones no observadas.
- Prioriza psicología del usuario, curiosidad, identificación con el problema, autoridad, educación, emoción, credibilidad y razones probables de engagement.
- Si la evidencia visual o textual no alcanza para concluir algo, escribe exactamente: "No hay suficiente evidencia para afirmar esa conclusión."
- Cuando el usuario pida análisis, responde con este formato:
  POR QUÉ FUNCIONA:
  - Insight 1
  - Insight 2
  - Insight 3
  EVIDENCIA:
  - Views
  - Likes
  - Comentarios
  - Shares
  APLICACIÓN PARA PIOLET:
  - Acción concreta
- Máximo 120 palabras.
- Si el usuario solo saluda o conversa, no hagas análisis.

Si el usuario pide un reporte, escríbelo siempre en español, con tono profesional y claro.
La sección final debe llamarse "CONCLUSION EJECUTIVA" y debe explicar por qué funcionaron los videos observados.
La conclusión debe basarse en evidencia y razones de engagement, no en escenas inventadas.
Responde siempre en español.
""".strip()

SYSTEM_PROMPT_AMBIGUO = """
No quedó claro si el usuario quiere una respuesta general o un análisis de videos/datos.
Pide una aclaración breve y natural, en español, sin analizar todavía.
""".strip()


def get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "Falta la API key de OpenRouter. Configura OPEN_ROUTER_KEY o OPENROUTER_API_KEY en Secrets."
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        http_client=httpx.Client(trust_env=False),
        default_headers={
            "HTTP-Referer": "https://pixelen.dev",
            "X-Title":      "Piolet Market Intel",
        },
    )


def _safe_chat_text(*, model: str, messages: list[dict], max_tokens: int, fallback: str) -> str:
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception as e:
        print(f"[OpenRouterError][_safe_chat_text] {type(e).__name__}: {e}")
    return fallback


INTENCION_CONVERSACION = "conversation"
INTENCION_RANKING = "ranking"
INTENCION_COMPARACION = "comparison"
INTENCION_RECOMENDACIONES = "recommendations"
INTENCION_ANALISIS_INDIVIDUAL = "analysis_individual"
INTENCION_ANALISIS = INTENCION_ANALISIS_INDIVIDUAL
INTENCION_PLATAFORMA = "platform"
INTENCION_AMBIGUA = "ambiguous"


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def _normalizar_texto(texto: str) -> str:
    texto = _strip_accents((texto or "").strip().lower())
    texto = re.sub(r"\s+", " ", texto)
    return texto


def clasificar_intencion(pregunta: str, historial: list[dict] | None = None) -> str:
    texto = _normalizar_texto(pregunta)
    if not texto:
        return INTENCION_CONVERSACION

    greetings = (
        "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
        "que tal", "que onda", "hey", "saludos",
    )
    thanks = ("gracias", "muchas gracias", "te agradezco", "agradezco")
    bye = ("adios", "hasta luego", "nos vemos", "bye", "chao", "cuidate")
    platform_phrases = (
        "que hace la plataforma", "para que sirve", "como funciona",
        "que puedo hacer", "que hace piolet", "que hace este dashboard",
        "explicame la plataforma", "que es piolet", "dashboard",
        "reporte pdf", "descargar pdf", "filtros", "videos analizados",
        "cuentas analizadas",
    )
    ranking_phrases = (
        "mejor desempeno", "mejor rendimiento", "funcionan mejor",
        "funciona mejor", "mejores videos", "top 5", "top videos",
        "mas virales", "mas viral", "ranking", "desempeno",
        "cuentas tienen mejor", "cuentas con mejor", "cuentas mas virales",
        "videos funcionan mejor", "cuales fueron los mas virales",
        "cuales son los mas virales", "cuentas tienen mejor desempeno",
    )
    comparison_phrases = (
        "compar", "vs", "contra", "diferencia", "entre tiktok e instagram",
        "entre cuentas", "entre plataformas", "cual plataforma", "que plataforma",
        "mejor que", "peor que", "por plataforma", "comparativo",
    )
    recommendation_phrases = (
        "que deberia copiar", "deberia copiar", "recomendaciones",
        "que tendencias observas", "tendencias observas", "que harias",
        "que publicaria", "que publicar", "como mejorar", "sugerencias",
        "ideas de contenido", "ideas", "accionables", "optimizar",
    )
    analysis_phrases = (
        "analiza este video", "analiza ese video", "dame la historia",
        "historia de este video", "historia del video", "explica el hook",
        "explica este video", "analisis individual", "arco emocional",
        "mensaje implicito", "narrativa", "hook del video", "gancho",
        "analiza", "analisis", "analizar", "por que se hizo viral",
        "por que funciona", "video especifico", "este video", "ese video",
    )

    if texto in greetings or any(texto.startswith(item + " ") for item in greetings):
        return INTENCION_CONVERSACION
    if texto in thanks or texto in bye:
        return INTENCION_CONVERSACION
    if any(phrase in texto for phrase in platform_phrases):
        return INTENCION_PLATAFORMA
    if any(phrase in texto for phrase in ranking_phrases):
        return INTENCION_RANKING
    if any(phrase in texto for phrase in comparison_phrases):
        return INTENCION_COMPARACION
    if any(phrase in texto for phrase in recommendation_phrases):
        return INTENCION_RECOMENDACIONES
    if re.fullmatch(r"(este|ese|aqui|ahi)\s+(video|contenido|reel|post|clip)", texto):
        return INTENCION_ANALISIS_INDIVIDUAL
    if any(phrase in texto for phrase in analysis_phrases):
        return INTENCION_ANALISIS_INDIVIDUAL
    if "?" in texto and len(texto.split()) <= 4:
        return INTENCION_CONVERSACION
    return INTENCION_CONVERSACION


def _system_prompt_for_intent(intencion: str) -> str:
    if intencion == INTENCION_RANKING:
        return """
Eres un analista de rendimiento de video.
Responde solo con ranking o comparativos breves basados en los datos disponibles.
Reglas:
- Si preguntan por videos o cuentas que funcionan mejor, devuelve 3 a 5 elementos máximo.
- Incluye métricas reales del dataset: views, likes, comments, engagement_rate y viral_score cuando estén disponibles.
- Explica en una frase breve por que aparecen arriba.
- No inventes historias ni escenas.
- No inventes datos que no estén en el contexto.
Responde en español.
""".strip()
    if intencion == INTENCION_COMPARACION:
        return """
Eres un analista comparativo.
Responde con diferencias claras entre cuentas, plataformas o grupos.
Reglas:
- Compara solo con evidencia del contexto.
- Prioriza tablas cortas, bullets o un resumen breve.
- Explica la diferencia principal y una implicacion accionable.
- No inventes historias ni escenas.
Responde en español.
""".strip()
    if intencion == INTENCION_RECOMENDACIONES:
        return """
Eres un estratega de contenido.
Responde con recomendaciones accionables, sin historia completa del video.
Reglas:
- Da insights concretos y aplicables.
- Enfocate en que copiar, que probar y que evitar.
- Si hay evidencia, menciona por que funciona.
- No inventes historias ni escenas salvo que el usuario lo pida explicitamente.
Responde en español.
""".strip()
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        return SYSTEM_PROMPT_ANALISIS
    if intencion == INTENCION_AMBIGUA:
        return SYSTEM_PROMPT_AMBIGUO
    if intencion == INTENCION_PLATAFORMA:
        return SYSTEM_PROMPT_CONVERSACION
    return SYSTEM_PROMPT_CONVERSACION


def _build_user_message(
    pregunta: str,
    context_data: str,
    intencion: str,
) -> str:
    if intencion in {
        INTENCION_RANKING,
        INTENCION_COMPARACION,
        INTENCION_RECOMENDACIONES,
        INTENCION_ANALISIS_INDIVIDUAL,
    }:
        return f"{pregunta}\n\n[DATOS]\n{context_data}"
    return pregunta


def _model_for_intent(intencion: str) -> str:
    if intencion in {
        INTENCION_RANKING,
        INTENCION_COMPARACION,
        INTENCION_RECOMENDACIONES,
        INTENCION_ANALISIS_INDIVIDUAL,
    }:
        return MODELO_ANALISIS
    return MODELO_CONVERSACION


def _max_tokens_for_intent(intencion: str) -> int:
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        return 1200
    if intencion in {INTENCION_RANKING, INTENCION_COMPARACION, INTENCION_RECOMENDACIONES}:
        return 900
    return 800


def _extraer_contenido(choice) -> str:
    """Extrae el texto de la respuesta, compatible con modelos de razonamiento (content=None)."""
    content = choice.message.content
    if content:
        return content
    # Modelos de razonamiento (nemotron, o1, etc.) usan el campo reasoning
    reasoning = getattr(choice.message, "reasoning", None)
    if reasoning:
        return reasoning
    reasoning_details = getattr(choice.message, "reasoning_details", None)
    if reasoning_details:
        return " ".join(d.get("text", "") for d in reasoning_details if isinstance(d, dict))
    return ""


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    if line.endswith(":"):
        return True
    if re.fullmatch(r"[A-Z0-9 \-/()]{4,}", line):
        return True
    return False


def _normalize_for_pdf(text: str) -> str:
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
        "\u2022": "-",
        "\u25a0": "-",
        "\ufeff": "",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKC", text)
    return text


def _extract_report_sections(report_text: str) -> dict[str, list[str]]:
    sections = {"top5": [], "oportunidades": [], "conclusion": []}
    current_section = None

    for raw_line in report_text.splitlines():
        line = _normalize_for_pdf(raw_line.strip())
        if not line or line.startswith("```") or line.startswith("|"):
            continue

        upper = line.upper().replace(":", "")
        if "TOP 5 VIDEOS" in upper:
            current_section = "top5"
            continue
        if "OPORTUNIDADES PARA PIOLET" in upper:
            current_section = "oportunidades"
            continue
        if "CONCLUSION EJECUTIVA" in upper:
            current_section = "conclusion"
            continue

        if current_section:
            sections[current_section].append(line)

    return sections


def _top_5_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.sort_values("views", ascending=False)
        .head(5)
        .copy()
    )


def _detalle_video_nemotron(row: pd.Series) -> str:
    client = get_client()
    prompt = (
        "En una sola frase en español, explica por que este video se hizo viral. "
        "Usa un tono claro y accionable. Solo texto final.\n\n"
        f"Cuenta: {row.get('account', 'unknown')}\n"
        f"Views: {int(row.get('views', 0))}\n"
        f"Viral score: {float(row.get('viral_score', 0)):.2f}\n"
        f"Descripcion: {str(row.get('description', ''))[:220]}\n"
        f"Hashtags: {str(row.get('hashtags', ''))[:160]}\n"
        f"URL: {row.get('url', '')}"
    )
    try:
        resp = client.chat.completions.create(
            model=MODELO_ANALISIS,
            messages=[
                {"role": "system", "content": "Responde solo en español y solo con el texto final."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=120,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass
    return _inferir_motivo_video(str(row.get("description", "")))


def _detalle_video_nemotron_v2(row: pd.Series) -> str:
    client = get_client()
    contexto = (
        f"Cuenta: {row.get('account', 'unknown')}\n"
        f"Views: {int(row.get('views', 0))}\n"
        f"Viral score: {float(row.get('viral_score', 0)):.2f}\n"
        f"Descripcion: {str(row.get('description', ''))[:220]}\n"
        f"Hashtags: {str(row.get('hashtags', ''))[:160]}\n"
        f"URL: {row.get('url', '')}"
    )
    prompt = (
        "Explica en una sola frase completa por que este video se hizo viral. "
        "Debe sonar natural, accionable y terminar con punto final. Solo texto final.\n\n"
        f"{contexto}"
    )

    def _complete(texto: str) -> str:
        texto = (texto or "").strip()
        if not texto:
            return texto
        if texto[-1] in ".!?":
            return texto
        try:
            resp2 = client.chat.completions.create(
                model=MODELO_REPORTE,
                messages=[
                    {"role": "system", "content": "Responde solo en español y solo con el texto final."},
                    {"role": "user", "content": (
                        "Termina exactamente el texto siguiente sin repetirlo y sin cambiar el sentido. "
                        "Devuelve solo la continuación y ciérrala con punto final.\n\n"
                        f"{texto}\n\nContexto:\n{contexto}"
                    )},
                ],
                max_tokens=120,
            )
            extra = (resp2.choices[0].message.content or "").strip()
            if extra:
                texto = f"{texto} {extra}".strip()
        except Exception:
            pass
        if texto and texto[-1] not in ".!?":
            texto += "."
        return texto

    try:
        resp = client.chat.completions.create(
            model=MODELO_ANALISIS,
            messages=[
                {"role": "system", "content": "Responde solo en español y solo con el texto final."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=140,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text.startswith("We need") or text.startswith("User wants"):
            text = ""
        if not text:
            resp = client.chat.completions.create(
                model=MODELO_REPORTE,
                messages=[
                    {"role": "system", "content": "Responde solo en español y solo con el texto final."},
                    {"role": "user", "content": (
                        "Devuelve solo una frase final y completa, sin explicación previa.\n\n"
                        f"{contexto}"
                    )},
                ],
                max_tokens=100,
            )
            text = (resp.choices[0].message.content or "").strip()
        text = _complete(text)
        if text:
            return text
    except Exception:
        pass
    return _inferir_motivo_video(str(row.get("description", "")))


def _analisis_resultados_video(row: pd.Series) -> str:
    client = get_client()
    descripcion = str(row.get("description", "")).strip()
    hashtags = str(row.get("hashtags", "")).strip()
    views = int(row.get("views", 0))
    likes = int(row.get("likes", 0))
    comments = int(row.get("comments", 0))
    shares = int(row.get("shares", 0))
    viral_score = float(row.get("viral_score", 0))
    pilares = _detectar_pilares_video(row)

    contexto = (
        f"Cuenta: {row.get('account', 'unknown')}\n"
        f"Views: {views}\n"
        f"Likes: {likes}\n"
        f"Comentarios: {comments}\n"
        f"Shares: {shares}\n"
        f"Viral score: {viral_score:.2f}\n"
        f"Descripcion: {descripcion[:240]}\n"
        f"Hashtags: {hashtags[:180]}\n"
        f"Pilares detectados: {', '.join(pilares)}\n"
        f"URL: {row.get('url', '')}"
    )
    prompt = (
        "Analiza por que obtuvo resultados, no describas el video.\n"
        "Reglas obligatorias:\n"
        "- Prohibido inventar escenas, sonidos, gestos, movimientos de camara o emociones no observadas.\n"
        "- Toda afirmacion debe estar respaldada por una observacion explicita del contexto.\n"
        "- Si la evidencia es insuficiente, responde exactamente: 'No hay suficiente evidencia para afirmar esa conclusión.'\n"
        "- Prioriza psicologia del usuario, curiosidad, identificacion con el problema, autoridad, educacion, emocion, credibilidad y razones probables de engagement.\n"
        "- Devuelve solo este formato:\n"
        "POR QUE FUNCIONA:\n"
        "- Insight 1\n"
        "- Insight 2\n"
        "- Insight 3\n"
        "EVIDENCIA:\n"
        f"- Views: {views}\n"
        f"- Likes: {likes}\n"
        f"- Comentarios: {comments}\n"
        f"- Shares: {shares}\n"
        "APLICACION PARA PIOLET:\n"
        "- Accion concreta\n"
        "Maximo 120 palabras.\n\n"
        f"{contexto}"
    )

    def _fallback() -> str:
        if views <= 0 and likes <= 0 and comments <= 0 and shares <= 0 and not descripcion and not hashtags:
            return "No hay suficiente evidencia para afirmar esa conclusión."
        insights = []
        if viral_score >= 2:
            insights.append("El rendimiento sugiere interes rapido o una propuesta que detiene el scroll.")
        if likes > 0 or comments > 0 or shares > 0:
            insights.append("La interaccion indica que el contenido conecta con una necesidad, aspiracion o prueba social.")
        if any("educativo" in p or "cientifico" in p for p in pilares):
            insights.append("La explicacion o el beneficio concreto ayudan a construir autoridad y confianza.")
        elif any("prueba social" in p or "credibilidad" in p for p in pilares):
            insights.append("La credibilidad aparente reduce friccion y vuelve mas facil compartir o considerar la compra.")
        elif any("promocion" in p or "llamada a la accion" in p for p in pilares):
            insights.append("La urgencia comercial puede elevar la accion inmediata.")
        else:
            insights.append("La evidencia disponible no permite afirmar una causa visual especifica.")
        return (
            "POR QUE FUNCIONA:\n"
            f"- {insights[0]}\n"
            f"- {insights[1] if len(insights) > 1 else 'No hay suficiente evidencia para afirmar esa conclusión.'}\n"
            f"- {insights[2] if len(insights) > 2 else 'No hay suficiente evidencia para afirmar esa conclusión.'}\n"
            "EVIDENCIA:\n"
            f"- Views: {views}\n"
            f"- Likes: {likes}\n"
            f"- Comentarios: {comments}\n"
            f"- Shares: {shares}\n"
            "APLICACION PARA PIOLET:\n"
            "- Replicar el angulo con un beneficio claro y una accion concreta."
        )

    try:
        resp = client.chat.completions.create(
            model=MODELO_REPORTE,
            messages=[
                {"role": "system", "content": "Responde en espanol. No describas escenas. No inventes informacion. Devuelve solo el formato pedido y maximo 120 palabras."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
        )
        text = _normalize_for_pdf((resp.choices[0].message.content or "").strip())
        if not text:
            return _fallback()
        lowered = text.lower()
        banned_terms = ("escena", "cámara", "camara", "mano", "pie", "sonido", "gesto", "movimiento", "temblor", "narrativa", "hook", "historia del video", "arco emocional")
        if any(term in lowered for term in banned_terms):
            return _fallback()
        if len(text.split()) > 120:
            return _fallback()
        if "no hay suficiente informacion" in lowered or "no hay suficiente evidencia" in lowered:
            return "No hay suficiente evidencia para afirmar esa conclusión."
        return text
    except Exception:
        return _fallback()


def _detalle_video_nemotron_v2(row: pd.Series) -> str:
    return _analisis_resultados_video(row)


def build_report_pdf(report_text: str, output_path: str | None = None) -> bytes:
    """Convierte el reporte en PDF y retorna los bytes listos para descarga."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Piolet - Reporte automatico",
        author="Piolet Market Intelligence",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=12,
        textColor=colors.HexColor("#1f2937"),
    ))
    styles.add(ParagraphStyle(
        name="ReportMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        spaceBefore=8,
        spaceAfter=6,
        textColor=colors.HexColor("#111827"),
    ))
    styles.add(ParagraphStyle(
        name="Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1f2937"),
        alignment=TA_LEFT,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BulletBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        leftIndent=16,
        firstLineIndent=0,
        spaceAfter=2,
        textColor=colors.HexColor("#1f2937"),
    ))
    styles.add(ParagraphStyle(
        name="SmallBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#374151"),
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="LinkBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.25,
        leading=11,
        textColor=colors.HexColor("#2563eb"),
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="DetailBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12,
        leftIndent=14,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=4,
    ))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawRightString(7.2 * inch, 0.45 * inch, f"Pagina {doc.page}")
        canvas.restoreState()

    story = [
        Paragraph("Piolet Market Intelligence", styles["ReportTitle"]),
        Paragraph("Reporte automatico del analisis de videos", styles["ReportMeta"]),
        Spacer(1, 0.12 * inch),
    ]

    sections = _extract_report_sections(report_text)

    if sections["top5"]:
        story.append(Paragraph("TOP 5 VIDEOS MAS VIRALES", styles["SectionHeading"]))
        i = 0
        while i < len(sections["top5"]):
            line = sections["top5"][i].strip()
            if not line:
                i += 1
                continue
            if " - URL: " in line:
                line, url = line.rsplit(" - URL: ", 1)
            else:
                url = ""
            story.append(Paragraph(html.escape(line), styles["BulletBody"], bulletText="-"))
            i += 1
            if i < len(sections["top5"]) and sections["top5"][i].startswith("Detalle:"):
                detail = sections["top5"][i].split("Detalle:", 1)[1].strip()
                story.append(Paragraph(html.escape(detail), styles["DetailBody"]))
                i += 1
            if i < len(sections["top5"]) and sections["top5"][i].startswith("URL:"):
                url_line = sections["top5"][i].split("URL:", 1)[1].strip()
                safe_url = html.escape(url_line or url, quote=True)
                if safe_url:
                    story.append(Paragraph(f'URL: <a href="{safe_url}">Abrir video</a>', styles["LinkBody"]))
                i += 1
        story.append(Spacer(1, 0.12 * inch))

    if sections["oportunidades"]:
        story.append(Paragraph("OPORTUNIDADES PARA PIOLET", styles["SectionHeading"]))
        for line in sections["oportunidades"][:4]:
            cleaned = line.lstrip("-*0123456789. ").strip()
            story.append(Paragraph(html.escape(cleaned), styles["BulletBody"], bulletText="-"))
        story.append(Spacer(1, 0.12 * inch))

    if sections["conclusion"]:
        conclusion_text = " ".join(
            line.lstrip("-*0123456789. ").strip()
            for line in sections["conclusion"]
        )
        conclusion_text = re.sub(r"\s+", " ", conclusion_text).strip()
        box = Table([[Paragraph(conclusion_text, styles["Body"])]] , colWidths=[6.55 * inch])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d1d5db")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(KeepTogether([
            Paragraph("CONCLUSION EJECUTIVA", styles["SectionHeading"]),
            box,
        ]))

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes


def cargar_datos() -> tuple[pd.DataFrame, str]:
    df = (
        pd.read_csv(DATA_PATH, index_col="rank")
        .replace(r"^\s*$", pd.NA, regex=True)
        .dropna(how="all")
    )

    top_videos = df.head(30)[
        ["platform", "account", "views", "likes", "comments",
         "shares", "engagement_rate", "viral_score", "description",
         "hashtags", "duration_secs"]
    ]

    stats = df.groupby(["platform", "account"]).agg(
        videos=("views", "count"),
        views_promedio=("views", "mean"),
        views_max=("views", "max"),
        engagement_promedio=("engagement_rate", "mean"),
        viral_count=("viral_score", lambda x: (x > 2).sum()),
    ).round(0)

    context = f"""
=== DATOS DE MERCADO: COLD PLUNGE / TINAS DE HIELO ===

ESTADÍSTICAS POR CUENTA:
{stats.to_string()}

TOP 30 VIDEOS POR VIEWS:
{top_videos.to_string()}

Total de videos analizados: {len(df)}
Plataformas: {df['platform'].unique().tolist()}
Cuentas trackeadas: {df['account'].unique().tolist()}
""".strip()

    return df, context


def _inferir_motivo_video(description: str) -> str:
    text = (description or "").lower()
    if "black" in text or "corporate" in text or "approved" in text:
        return "humor corporativo y FOMO"
    if "epsom" in text or "salts" in text or "magnesium" in text:
        return "valor educativo y beneficio funcional"
    if "women" in text or "menopause" in text or "female" in text:
        return "mensaje para mujeres y mito de nicho"
    if "hair" in text or "light environment" in text:
        return "beneficio especifico y curiosidad"
    if "podcast" in text or "link in bio" in text:
        return "prueba social y CTA directo"
    if "athlete" in text or "athletic" in text or "movement coach" in text:
        return "credibilidad deportiva y aspiracional"
    return "gancho claro y formato corto"


def _detectar_pilares_video(row: pd.Series) -> list[str]:
    texto = " ".join(
        [
            str(row.get("account", "")),
            str(row.get("description", "")),
            str(row.get("hashtags", "")),
        ]
    ).lower()
    pilares: list[str] = []

    def agregar(pilar: str) -> None:
        if pilar not in pilares:
            pilares.append(pilar)

    if any(k in texto for k in ["cold plunge", "coldplunge", "ice bath", "icebath", "ice barrel", "vasoconstriction", "cold water", "recovery", "wellness", "plunge"]):
        agregar("la tendencia del cold plunge como ritual de bienestar y recuperacion")
    if any(k in texto for k in ["how", "what", "why", "benefit", "benefits", "science", "educ", "vasoconstriction", "sleep", "stress", "magnesium", "epsom", "tutorial", "explaining"]):
        agregar("una explicacion simple del beneficio tecnico o cientifico")
    if any(k in texto for k in ["sale", "discount", "black friday", "offer", "limited", "link in bio", "buy", "shop", "order", "promo", "launch"]):
        agregar("una promocion limitada con llamada a la accion clara")
    if any(k in texto for k in ["funny", "humor", "lol", "fear", "scary", "creepy", "reaction", "challenge", "surprised", "wow", "fun"]):
        agregar("una situacion inesperada que activa humor o curiosidad")
    if any(k in texto for k in ["athlete", "athletic", "coach", "performance", "training", "gym", "fit", "fitness", "women", "menopause", "community", "testimonial", "client"]):
        agregar("prueba social o credibilidad aspiracional")
    if any(k in texto for k in ["motiv", "mindset", "discipline", "routine", "consistency", "habit", "mindful"]):
        agregar("un mensaje motivador que invita a la accion")

    if not pilares:
        pilares.append("un gancho claro y un formato breve de consumo rapido")
    return pilares


def _detalle_video_descriptivo(row: pd.Series) -> str:
    client = get_client()
    pilares = _detectar_pilares_video(row)
    descripcion = str(row.get("description", "")).strip()
    hashtags = str(row.get("hashtags", "")).strip()
    contexto = (
        f"Cuenta: {row.get('account', 'unknown')}\n"
        f"Views: {int(row.get('views', 0))}\n"
        f"Viral score: {float(row.get('viral_score', 0)):.2f}\n"
        f"Descripcion: {descripcion[:220]}\n"
        f"Hashtags: {hashtags[:160]}\n"
        f"URL: {row.get('url', '')}"
    )
    prompt = (
        "Escribe exactamente 2 frases completas en espanol para un reporte de marketing. "
        "La primera frase debe empezar con: 'El video se volvió viral porque'. "
        "La segunda frase debe explicar por qué conecta con la audiencia y cerrar con una recomendacion implícita para Piolet. "
        "No uses viñetas, no expliques el proceso y no digas que eres un modelo.\n\n"
        f"Pilares detectados: {', '.join(pilares)}\n"
        f"{contexto}"
    )

    def _fallback() -> str:
        primera = f"El video se volvió viral porque combina {pilares[0]}"
        if len(pilares) > 1:
            primera += f" con {pilares[1]}"
        primera += "."
        segunda = "Ese cruce hace que el contenido se entienda rapido, genere curiosidad y deje claro por que la marca merece atencion."
        if any("promocion" in p or "llamada a la accion" in p for p in pilares):
            segunda = "Ese cruce acelera la decision de compra porque mezcla interes inmediato con una accion comercial muy clara."
        elif any("educativo" in p or "cientifico" in p for p in pilares):
            segunda = "Ese cruce funciona porque simplifica un beneficio tecnico en segundos y le da al espectador una razon concreta para confiar."
        elif any("humor" in p or "curiosidad" in p for p in pilares):
            segunda = "Ese cruce funciona porque abre un gancho emocional rapido, sostiene la atencion y deja una conclusion facil de compartir."
        elif any("motivador" in p for p in pilares):
            segunda = "Ese cruce funciona porque une aspiracion personal con una idea simple que el espectador puede imaginar aplicando de inmediato."
        elif any("prueba social" in p for p in pilares):
            segunda = "Ese cruce funciona porque convierte la experiencia en evidencia social y reduce la friccion para probar el producto."
        return f"{primera} {segunda}"

    try:
        resp = client.chat.completions.create(
            model=MODELO_REPORTE,
            messages=[
                {"role": "system", "content": "Responde solo en espanol y solo con las 2 frases finales."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=180,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            text = _normalize_for_pdf(text)
            if not text.lower().startswith("el video se volvió viral porque"):
                text = _fallback()
            elif text.count(".") < 2 or len(text) < 120:
                text = _fallback()
            return text
    except Exception:
        pass
    return _fallback()


def _oportunidades_reporte(top_df: pd.DataFrame) -> list[str]:
    reasons = top_df["description"].fillna("").astype(str).str.lower().tolist()
    if not reasons:
        return [
            "Crear reels de 15 a 30 segundos con gancho en los primeros 3 segundos y CTA de compra al final.",
            "Publicar piezas educativas sobre beneficios concretos: recuperacion, sueño, estres y rendimiento deportivo.",
            "Probar contenido dirigido a mujeres y atletas con testimonios reales y prueba social visible.",
            "Ligar picos comerciales como Buen Fin o Black Friday con humor corporativo y ofertas limitadas.",
        ]
    return [
        "Copiar el formato de gancho rapido del top viral y llevarlo a videos de 15 a 30 segundos con CTA directo.",
        "Construir piezas educativas que expliquen un beneficio concreto por video, como recuperacion, energia o sueño.",
        "Usar prueba social y testimonios reales para respaldar el producto y bajar friccion de compra.",
        "Anclar campañas a fechas comerciales con humor y urgencia para elevar alcance y conversion.",
    ]


def _conclusion_reporte_nemotron(top_lines: list[str], oportunidades: list[str]) -> str:
    client = get_client()
    prompt = (
        "Escribe una CONCLUSION EJECUTIVA de 3 frases en español para un reporte de cold plunge. "
        "Usa esta base: los videos destacaron por humor corporativo, educación cientifica, prueba social y CTA directo. "
        "Hazla clara, accionable y sin viñetas.\n\n"
        f"Top 5:\n" + "\n".join(top_lines) + "\n\n"
        f"Oportunidades:\n" + "\n".join(f"- {item}" for item in oportunidades)
    )
    respuesta = client.chat.completions.create(
        model=MODELO_REPORTE,
        messages=[
            {"role": "system", "content": "Responde solo en español y solo con el texto final."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=250,
    )
    conclusion = (respuesta.choices[0].message.content or "").strip()
    if conclusion:
        return conclusion
    return (
        "Los videos funcionaron por una combinacion de interes rapido, claridad del mensaje y evidencia que apoya la credibilidad. "
        "La interaccion observada sugiere que el contenido responde a una necesidad concreta y facilita que el usuario lo considere relevante. "
        "Piolet deberia replicar el angulo con una propuesta simple, un beneficio claro y una accion concreta."
    )


def _conclusion_reporte_nemotron(top_lines: list[str], oportunidades: list[str]) -> str:
    resumen_top = " ".join(top_lines[:5])
    prompt = (
        "Escribe una CONCLUSION EJECUTIVA de exactamente 3 frases en español para un reporte de cold plunge. "
        "Debe ser clara, concreta y terminar con punto final. "
        "No uses viñetas ni encabezados adicionales.\n\n"
        f"Top 5:\n" + "\n".join(top_lines) + "\n\n"
        f"Oportunidades:\n" + "\n".join(f"- {item}" for item in oportunidades) + "\n\n"
        f"Resumen extra: {resumen_top}"
    )

    def _fallback() -> str:
        return (
            "Los videos funcionaron por una combinacion de interes rapido, claridad del mensaje y evidencia que apoya la credibilidad. "
            "La interaccion observada sugiere que el contenido responde a una necesidad concreta y facilita que el usuario lo considere relevante. "
            "Piolet deberia replicar el angulo con una propuesta simple, un beneficio claro y una accion concreta."
        )

    conclusion = _safe_chat_text(
        model=MODELO_REPORTE,
        messages=[
            {"role": "system", "content": "Responde solo en espanol y solo con el texto final."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=220,
        fallback="",
    )
    conclusion = _normalize_for_pdf(conclusion)
    if not conclusion or len(conclusion) < 180 or conclusion.count(".") < 3:
        return _fallback()
    return conclusion


def agente_interactivo():
    client = get_client()

    print("\n" + "="*60)
    print(f" AGENTE PIOLET — {MODELO_CONVERSACION}")
    print("="*60)

    if not os.path.exists(DATA_PATH):
        print("[Error] No hay datos. Corre primero: python scraper.py")
        return

    df, context_data = cargar_datos()
    print(f"[OK] {len(df)} videos de {df['account'].nunique()} cuentas cargados")
    print("\nEscribe tu pregunta o 'salir' para terminar.")
    print("Ejemplos:")
    print("  - ¿Qué tipo de videos generan más views en TikTok?")
    print("  - ¿Qué duración tienen los videos más virales?")
    print("  - Dame 5 ideas de contenido para Piolet")
    print("  - ¿Qué hashtags usa la competencia en sus mejores videos?\n")

    historial = []

    while True:
        pregunta = input("Tú: ").strip()
        if pregunta.lower() in ["salir", "exit", "quit"]:
            print("Agente: Hasta luego.")
            break
        if not pregunta:
            continue

        intencion = clasificar_intencion(pregunta, historial)
        user_message = _build_user_message(pregunta, context_data, intencion)
        historial.append({"role": "user", "content": user_message})

        print("\nAgente: ", end="", flush=True)
        respuesta_completa = ""

        if intencion == INTENCION_AMBIGUA:
            respuesta_completa = (
                "No me quedó claro si quieres una respuesta general o un análisis de videos. "
                "Si quieres, te respondo normal o analizo los videos del tablero."
            )
            print(respuesta_completa, end="", flush=True)
        elif intencion in {INTENCION_CONVERSACION, INTENCION_PLATAFORMA}:
            respuesta_completa = _local_chat_reply(pregunta, intencion)
            print(respuesta_completa, end="", flush=True)
        else:
            model = _model_for_intent(intencion)
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": _system_prompt_for_intent(intencion)}] + historial,
                max_tokens=_max_tokens_for_intent(intencion),
                stream=True,
            )
            for chunk in stream:
                texto = chunk.choices[0].delta.content or ""
                print(texto, end="", flush=True)
                respuesta_completa += texto

        print("\n")
        historial.append({"role": "assistant", "content": respuesta_completa})

        os.makedirs("datos", exist_ok=True)
        with open("datos/sesion_agente.json", "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)


def analisis_automatico(df_base: pd.DataFrame | None = None) -> str:
    if df_base is None and not os.path.exists(DATA_PATH):
        return "[Error] No hay datos. Corre primero: python scraper.py"

    if df_base is None:
        df, _ = cargar_datos()
    else:
        df = df_base.copy()
    top_df = _top_5_dashboard(df)
    top_items = []
    top_5_lines = []
    for _, row in top_df.iterrows():
        detalle = _detalle_video_nemotron_v2(row)
        top_items.append(
            {
                "account": row.get("account", "unknown"),
                "views": int(row.get("views", 0)),
                "viral_score": float(row.get("viral_score", 0)),
                "detail": detalle,
                "url": row.get("url", ""),
            }
        )
        top_5_lines.extend([
            f"{row.get('account', 'unknown')} - {int(row.get('views', 0)):,} vistas - viral {float(row.get('viral_score', 0)):.2f}",
            f"Detalle: {detalle}",
            f"URL: {row.get('url', '')}",
        ])

    oportunidades = _oportunidades_reporte(top_df)
    conclusion = _conclusion_reporte_nemotron(
        [
            f"{item['account']} | views={item['views']} | viral={item['viral_score']:.2f} | {item['detail']}"
            for item in top_items
        ],
        oportunidades,
    )

    reporte = "\n".join(
        [
            "TOP 5 VIDEOS MAS RELEVANTES",
            *top_5_lines,
            "",
            "OPORTUNIDADES PARA PIOLET",
            *[f"- {item}" for item in oportunidades],
            "",
            "CONCLUSION EJECUTIVA",
            conclusion,
        ]
    )

    os.makedirs("datos", exist_ok=True)
    with open("datos/reporte_automatico.txt", "w", encoding="utf-8") as f:
        f.write(reporte)

    return reporte


def stream_respuesta(
    historial: list[dict],
    pregunta: str,
    context_data: str,
    intencion: str | None = None,
):
    """Generador de chunks para st.write_stream en dashboard.py"""
    if intencion is None:
        intencion = clasificar_intencion(pregunta, historial)
    user_message = _build_user_message(pregunta, context_data, intencion)
    mensajes = (
        [{"role": "system", "content": _system_prompt_for_intent(intencion)}]
        + historial
        + [{"role": "user", "content": user_message}]
    )

    if intencion == INTENCION_AMBIGUA:
        yield (
            "No me quedó claro si quieres una respuesta general o un análisis de videos. "
            "Si quieres, te respondo normal o analizo los videos del tablero."
        )
        return

    try:
        client = get_client()
        model = _model_for_intent(intencion)
        resp = client.chat.completions.create(
            model=model,
            messages=mensajes,
            max_tokens=_max_tokens_for_intent(intencion),
        )
        yield _extraer_contenido(resp.choices[0])
    except Exception:
        if intencion in {
            INTENCION_RANKING,
            INTENCION_COMPARACION,
            INTENCION_RECOMENDACIONES,
            INTENCION_ANALISIS_INDIVIDUAL,
        }:
            yield (
                "No pude consultar el modelo de analisis en este momento. "
                "Puedo seguir trabajando con los datos locales cargados en el dashboard."
            )
        else:
            yield "No pude responder en este momento. Si quieres, intenta de nuevo en unos segundos."


SYSTEM_PROMPT_CONVERSACION = """
Eres el asistente de Piolet Market Intelligence.

Tu tarea es conversar de forma natural con el usuario.

Responde saludos, preguntas generales y dudas sobre la plataforma.

No generes analisis de videos a menos que el usuario lo solicite explicitamente.

Mantente breve, amable y claro.

Si preguntan que hace la plataforma, explica de forma simple que puede:
- analizar videos
- identificar patrones de viralidad
- comparar cuentas
- dar recomendaciones basadas en los datos disponibles
""".strip()

SYSTEM_PROMPT_ANALISIS = """
Eres un estratega senior de marketing digital.

Tu trabajo NO es describir el video.
Tu trabajo es explicar por que obtuvo resultados.

Reglas:
- No inventar escenas.
- No inventar emociones.
- No inventar sonidos.
- No inventar movimientos de camara.
- No reconstruir historias.

Analiza:
- Curiosidad
- Educacion
- Autoridad
- Credibilidad
- Psicologia del usuario
- Factores de viralidad

Respuesta maxima: 120 palabras.

Formato:

POR QUE FUNCIONO
- ...
- ...
- ...

APRENDIZAJE PARA PIOLET
- ...
- ...
""".strip()

SYSTEM_PROMPT_RANKING = """
Eres un analista de rendimiento de video.

Responde solo con ranking o comparativos breves basados en los datos disponibles.

Reglas:
- Devuelve de 3 a 5 elementos maximo.
- Incluye metricas reales del dataset cuando esten disponibles.
- Explica en una frase breve por que aparecen arriba.
- No inventes historias ni escenas.
- No inventes datos que no esten en el contexto.

Responde en espanol.
""".strip()

SYSTEM_PROMPT_RECOMENDACIONES = """
Eres un estratega de contenido.

Responde con recomendaciones accionables, sin narrar el video.

Reglas:
- Da insights concretos y aplicables.
- Enfocate en que copiar, que probar y que evitar.
- Si hay evidencia, menciona por que funciona.
- No inventes historias ni escenas salvo que el usuario lo pida explicitamente.

Responde en espanol.
""".strip()

SYSTEM_PROMPT_AMBIGUO = """
No quedo claro si el usuario quiere una respuesta general o un analisis de videos o datos.

Pide una aclaracion breve y natural en espanol.
No analices todavia.
""".strip()


def clasificar_intencion(pregunta: str, historial: list[dict] | None = None) -> str:
    texto = _normalizar_texto(pregunta)
    if not texto:
        return INTENCION_CONVERSACION

    greetings = (
        "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
        "que tal", "que onda", "hey", "saludos",
    )
    thanks = ("gracias", "muchas gracias", "te agradezco", "agradezco")
    bye = ("adios", "hasta luego", "nos vemos", "bye", "chao", "cuidate")
    platform_phrases = (
        "que hace la plataforma", "para que sirve", "como funciona",
        "que puedo hacer", "que hace piolet", "que hace este dashboard",
        "explicame la plataforma", "que es piolet", "dashboard",
        "reporte pdf", "descargar pdf", "filtros", "videos analizados",
        "cuentas analizadas", "ayuda", "quien eres", "quien eres tu",
    )
    ranking_phrases = (
        "mejor desempeno", "mejor rendimiento", "funcionan mejor",
        "funciona mejor", "mejores videos", "top 5", "top videos",
        "mas virales", "mas viral", "ranking", "desempeno",
        "cuentas tienen mejor", "cuentas con mejor", "cuentas mas virales",
        "videos funcionan mejor", "cuales fueron los mas virales",
        "cuales son los mas virales", "cuentas tienen mejor desempeno",
    )
    recommendation_phrases = (
        "que deberia copiar", "deberia copiar", "recomendaciones",
        "que tendencias observas", "tendencias observas", "que harias",
        "que publicaria", "que publicar", "como mejorar", "sugerencias",
        "ideas de contenido", "ideas", "accionables", "optimizar",
        "que estrategias estan funcionando", "estrategias estan funcionando",
    )
    analysis_phrases = (
        "analiza este video", "analiza ese video", "dame la historia",
        "historia de este video", "historia del video", "explica el hook",
        "explica este video", "analisis individual", "arco emocional",
        "mensaje implicito", "narrativa", "hook del video", "gancho",
        "analiza", "analisis", "analizar", "por que se hizo viral",
        "por que funciona", "por que funciono", "que podemos aprender",
        "que hizo bien", "este video", "ese video", "este contenido",
    )
    ambiguous_phrases = (
        "que opinas", "que piensas", "y este", "y esta", "y eso",
        "y este video", "y esta cuenta", "que tal este", "que tal esta",
        "cuentame mas", "dime mas", "esto?", "este?", "esa?",
    )

    if texto in greetings or any(texto.startswith(item + " ") for item in greetings):
        return INTENCION_CONVERSACION
    if texto in thanks or texto in bye:
        return INTENCION_CONVERSACION
    if any(phrase in texto for phrase in platform_phrases):
        return INTENCION_PLATAFORMA
    if any(phrase in texto for phrase in ranking_phrases):
        return INTENCION_RANKING
    if any(phrase in texto for phrase in recommendation_phrases):
        return INTENCION_RECOMENDACIONES
    if any(phrase in texto for phrase in ambiguous_phrases):
        return INTENCION_AMBIGUA
    if re.fullmatch(r"(este|ese|aqui|ahi)\s+(video|contenido|reel|post|clip|cuenta)", texto):
        return INTENCION_AMBIGUA
    if any(phrase in texto for phrase in analysis_phrases):
        return INTENCION_ANALISIS_INDIVIDUAL
    if "?" in texto and len(texto.split()) <= 4:
        return INTENCION_AMBIGUA
    return INTENCION_CONVERSACION


def _system_prompt_for_intent(intencion: str) -> str:
    if intencion == INTENCION_RANKING:
        return SYSTEM_PROMPT_RANKING
    if intencion == INTENCION_RECOMENDACIONES:
        return SYSTEM_PROMPT_RECOMENDACIONES
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        return SYSTEM_PROMPT_ANALISIS
    if intencion == INTENCION_AMBIGUA:
        return SYSTEM_PROMPT_AMBIGUO
    return SYSTEM_PROMPT_CONVERSACION


def _history_for_intent(historial: list[dict], intencion: str) -> list[dict]:
    if intencion not in {INTENCION_CONVERSACION, INTENCION_PLATAFORMA, INTENCION_AMBIGUA}:
        return historial

    sanitizado: list[dict] = []
    for msg in historial[-8:]:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))
        if "[DATOS]" in content:
            content = content.split("[DATOS]")[0].strip()
        content = content.strip()
        if content:
            sanitizado.append({"role": role, "content": content})
    return sanitizado


def _local_chat_reply(pregunta: str, intencion: str) -> str:
    texto = _normalizar_texto(pregunta)

    if intencion == INTENCION_PLATAFORMA:
        return (
            "Piolet Market Intelligence te ayuda a analizar videos, identificar patrones de viralidad, "
            "comparar cuentas y generar recomendaciones basadas en los datos disponibles."
        )

    if texto in {"hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "hey", "saludos"}:
        return (
            "Hola 👋 ¿En qué puedo ayudarte? Puedo analizar videos, identificar patrones de viralidad, "
            "comparar cuentas o darte recomendaciones basadas en los datos disponibles."
        )

    if "gracias" in texto:
        return "Con gusto. Si quieres, puedo ayudarte a analizar videos, comparar cuentas o sacar recomendaciones."

    if any(frase in texto for frase in ("quien eres", "quien eres tu", "ayuda")):
        return (
            "Soy el asistente de Piolet Market Intelligence. Puedo ayudarte a analizar videos, "
            "comparar cuentas, identificar patrones y sacar recomendaciones."
        )

    return (
        "Puedo ayudarte a analizar videos, comparar cuentas, identificar patrones de viralidad "
        "o darte recomendaciones basadas en los datos disponibles."
    )


def _local_ranking_reply(context_data: str, pregunta: str) -> str:
    texto = _normalizar_texto(pregunta)
    if "tiktok" in texto:
        plataforma = "TikTok"
    elif "instagram" in texto:
        plataforma = "Instagram"
    else:
        plataforma = "las plataformas disponibles"

    lines: list[str] = []
    for raw_line in context_data.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Top") or "viral score" in line.lower() or "views" in line.lower() or "cuentas trackeadas" in line.lower():
            lines.append(line)
    if not lines:
        return (
            f"En {plataforma}, los videos que mejor funcionan suelen ser los que combinan un gancho claro, "
            "beneficio concreto y una propuesta fácil de entender."
        )

    preview = lines[:6]
    cuerpo = "\n".join(f"- {line}" for line in preview)
    return (
        f"En {plataforma}, lo que mejor desempeño tiene en el tablero es esto:\n"
        f"{cuerpo}\n\n"
        "La razón probable es que esos contenidos mezclan gancho rápido, claridad del beneficio y señales de credibilidad."
    )


def _local_recommendations_reply(context_data: str, pregunta: str) -> str:
    texto = _normalizar_texto(pregunta)
    if "copiar" in texto or "deberia" in texto:
        return (
            "Yo copiaría tres cosas de lo que ya funciona: un gancho muy rápido, un beneficio concreto por video "
            "y una prueba clara de credibilidad o uso real.\n\n"
            "Para Piolet, eso se traduce en piezas cortas, directas y fáciles de consumir."
        )
    return (
        "Las estrategias que están funcionando suelen combinar curiosidad, beneficio claro y credibilidad.\n\n"
        "Para Piolet, la mejor jugada es hacer videos cortos, educativos y con una promesa concreta desde los primeros segundos."
    )


def _local_analysis_reply(context_data: str, pregunta: str) -> str:
    return (
        "POR QUE FUNCIONO\n"
        "- Tiene un gancho claro y rápido.\n"
        "- Comunica un beneficio o idea fácil de entender.\n"
        "- Suma credibilidad o curiosidad desde los primeros segundos.\n\n"
        "APRENDIZAJE PARA PIOLET\n"
        "- Mostrar beneficio concreto desde el inicio.\n"
        "- Evitar explicaciones largas.\n"
        "- Reforzar autoridad con evidencia simple."
    )


def _trim_text(text: str, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[recortado]..."


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _normalize_structured_result(data: dict, intencion: str) -> dict:
    if not isinstance(data, dict):
        data = {}

    if intencion == INTENCION_RANKING:
        data.setdefault("intent", "ranking")
        data.setdefault("top_videos", [])
        data.setdefault("patterns", [])
        data.setdefault("reasoning", [])
        data.setdefault("recommendations", [])
        return data
    if intencion == INTENCION_RECOMENDACIONES:
        data.setdefault("intent", "recommendations")
        data.setdefault("patterns", [])
        data.setdefault("reasoning", [])
        data.setdefault("recommendations", [])
        data.setdefault("top_videos", [])
        return data
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        data.setdefault("intent", "analysis_individual")
        data.setdefault("patterns", [])
        data.setdefault("reasoning", [])
        data.setdefault("takeaway", "")
        data.setdefault("recommendations", [])
        return data
    data.setdefault("intent", intencion)
    return data


def _nemotron_prompt_for_intent(intencion: str) -> str:
    if intencion == INTENCION_RANKING:
        return """
Eres Nemotron, motor analitico de Piolet.
Devuelve SOLO JSON valido.
Objetivo: identificar los videos o cuentas con mejor desempeno, detectar patrones y resumir razones probables de viralidad.
Formato:
{"intent":"ranking","top_videos":[{"account":"string","platform":"string","views":0,"viral_score":0,"note":"string"}],"patterns":["string"],"reasoning":["string"],"recommendations":["string"],"confidence":"high|medium|low"}
""".strip()
    if intencion == INTENCION_RECOMENDACIONES:
        return """
Eres Nemotron, motor analitico de Piolet.
Devuelve SOLO JSON valido.
Objetivo: detectar oportunidades accionables, resumir patrones de exito y proponer aprendizajes para Piolet.
Formato:
{"intent":"recommendations","patterns":["string"],"reasoning":["string"],"recommendations":["string"],"top_videos":[],"confidence":"high|medium|low"}
""".strip()
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        return """
Eres Nemotron, motor analitico de Piolet.
Devuelve SOLO JSON valido.
Objetivo: explicar por que el video funciona o no funciona, resumir causas probables de viralidad y extraer aprendizajes para Piolet.
Formato:
{"intent":"analysis_individual","patterns":["string"],"reasoning":["string"],"takeaway":"string","recommendations":["string"],"confidence":"high|medium|low"}
""".strip()
    return "Eres Nemotron, motor analitico de Piolet. Devuelve SOLO JSON valido."


def _gemma_prompt_for_intent(intencion: str) -> str:
    if intencion == INTENCION_AMBIGUA:
        return """
Eres Gemma, el agente conversacional de Piolet Market Intelligence.
El usuario hizo una pregunta ambigua. Pide una aclaracion breve, natural y amable en espanol. No inventes analisis.
""".strip()
    if intencion in {INTENCION_CONVERSACION, INTENCION_PLATAFORMA}:
        return """
Eres Gemma, el agente conversacional de Piolet Market Intelligence.
Tu tarea es conversar de forma natural con el usuario.
Responde saludos, preguntas generales y dudas sobre la plataforma.
No generes analisis de videos a menos que el usuario lo solicite explicitamente.
Mantente breve, amable y claro.
Responde en espanol como ChatGPT.
""".strip()
    if intencion == INTENCION_RANKING:
        return """
Eres Gemma, el agente conversacional de Piolet Market Intelligence.
Recibiste un resultado estructurado de Nemotron.
Tu trabajo es explicarlo de forma natural, breve y clara.
No recalcules metricas, no inventes datos nuevos y no describas escenas.
Responde en espanol como ChatGPT.
""".strip()
    if intencion == INTENCION_RECOMENDACIONES:
        return """
Eres Gemma, el agente conversacional de Piolet Market Intelligence.
Recibiste un resultado estructurado de Nemotron.
Tu trabajo es explicarlo de forma natural, breve y accionable.
No inventes datos nuevos ni recalcules metricas.
Responde en espanol como ChatGPT.
""".strip()
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        return """
Eres Gemma, el agente conversacional de Piolet Market Intelligence.
Recibiste un resultado estructurado de Nemotron.
Tu trabajo es explicarlo de forma natural, breve y convincente.
No inventes escenas, no recalcules metricas y no agregues datos nuevos.
Responde en espanol como ChatGPT.
""".strip()
    return "Eres Gemma, el agente conversacional de Piolet Market Intelligence. Responde en espanol como ChatGPT."


def _build_nemotron_messages(historial: list[dict], pregunta: str, context_data: str, intencion: str) -> list[dict]:
    return [
        {"role": "system", "content": _nemotron_prompt_for_intent(intencion)},
        *(_history_for_intent(historial, intencion)),
        {
            "role": "user",
            "content": (
                f"Pregunta del usuario:\n{pregunta}\n\n"
                f"Contexto de datos:\n{_trim_text(context_data)}\n\n"
                "Devuelve el JSON solicitado y nada mas."
            ),
        },
    ]


def _build_gemma_messages(
    historial: list[dict],
    pregunta: str,
    intencion: str,
    structured_result: dict | None = None,
) -> list[dict]:
    messages = [{"role": "system", "content": _gemma_prompt_for_intent(intencion)}]
    messages.extend(_history_for_intent(historial, INTENCION_CONVERSACION if intencion == INTENCION_AMBIGUA else intencion))
    if structured_result is None:
        messages.append({"role": "user", "content": pregunta})
    else:
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Pregunta del usuario:\n{pregunta}\n\n"
                    f"Resultado estructurado de Nemotron:\n{json.dumps(structured_result, ensure_ascii=False, indent=2)}\n\n"
                    "Explica esto al usuario de forma natural, breve y util."
                ),
            }
        )
    return messages


def _call_model_text(*, model: str, messages: list[dict], max_tokens: int) -> str:
    client = get_client()
    response = client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)
    return (response.choices[0].message.content or "").strip()


def _nemotron_structured_result(historial: list[dict], pregunta: str, context_data: str, intencion: str) -> dict:
    raw = _call_model_text(
        model=MODELO_ANALISIS,
        messages=_build_nemotron_messages(historial, pregunta, context_data, intencion),
        max_tokens=900,
    )
    parsed = _extract_json_object(raw)
    if not parsed:
        parsed = {"intent": intencion, "raw": raw}
    return _normalize_structured_result(parsed, intencion)


def _gemma_explain_result(
    historial: list[dict],
    pregunta: str,
    intencion: str,
    structured_result: dict | None = None,
) -> str:
    return _call_model_text(
        model=MODELO_CONVERSACION,
        messages=_build_gemma_messages(historial, pregunta, intencion, structured_result),
        max_tokens=700,
    )


def _openrouter_error_message(error: Exception, intencion: str) -> str:
    name = type(error).__name__.lower()
    message = str(error).lower()

    if "rate limit" in message or "rate_limit" in message or "429" in message or "free-models-per-day" in message:
        return (
            "OpenRouter alcanzo el limite diario de modelos gratis. "
            "Agrega creditos o espera al reset del limite para seguir usando los modelos gratuitos."
        )
    if "falta la api key" in message or "api key" in message or "openrouter" in message and "secrets" in message:
        return "Falta la API key de OpenRouter en Secrets o en el entorno del servidor."
    if "connect" in name or "connection" in message or "timeout" in name or "timed out" in message:
        return "No pude conectar con OpenRouter. Revisa red, proxy o acceso desde el servidor."
    if "auth" in name or "401" in message or "403" in message or "unauthorized" in message:
        return "La API key de OpenRouter no es válida o no tiene permisos para ese modelo."
    if "badrequest" in name or "404" in message or "model" in message and ("not found" in message or "does not exist" in message):
        return "El modelo configurado en OpenRouter no está disponible."
    if intencion == INTENCION_ANALISIS_INDIVIDUAL:
        return "No pude consultar OpenRouter para el análisis. Revisa la clave, red y disponibilidad del modelo."
    return "No pude consultar OpenRouter. Revisa la clave, la red y la disponibilidad del modelo."


def stream_respuesta(
    historial: list[dict],
    pregunta: str,
    context_data: str,
    intencion: str | None = None,
):
    """Generador de chunks para st.write_stream en dashboard.py"""
    if intencion is None:
        intencion = clasificar_intencion(pregunta, historial)
    if intencion == INTENCION_AMBIGUA:
        try:
            yield _gemma_explain_result(historial, pregunta, intencion)
        except Exception as e:
            print(f"[OpenRouterError][stream_respuesta][gemma-ambiguous] {type(e).__name__}: {e}")
            yield "No me quedo claro si quieres una respuesta general o un analisis de videos. Si quieres, dime si buscas ranking, analisis o recomendaciones."
        return
    if intencion in {INTENCION_CONVERSACION, INTENCION_PLATAFORMA}:
        try:
            yield _gemma_explain_result(historial, pregunta, intencion)
        except Exception as e:
            print(f"[OpenRouterError][stream_respuesta][gemma-chat] {type(e).__name__}: {e}")
            yield _local_chat_reply(pregunta, intencion)
        return
    if intencion in {INTENCION_RANKING, INTENCION_RECOMENDACIONES, INTENCION_ANALISIS_INDIVIDUAL, INTENCION_COMPARACION}:
        try:
            structured = _nemotron_structured_result(historial, pregunta, context_data, intencion)
        except Exception as e:
            print(f"[OpenRouterError][stream_respuesta][nemotron] intent={intencion} error={type(e).__name__}: {e}")
            if intencion == INTENCION_RANKING:
                yield _local_ranking_reply(context_data, pregunta)
            elif intencion == INTENCION_RECOMENDACIONES:
                yield _local_recommendations_reply(context_data, pregunta)
            elif intencion == INTENCION_ANALISIS_INDIVIDUAL:
                yield _local_analysis_reply(context_data, pregunta)
            else:
                yield _local_ranking_reply(context_data, pregunta)
            return

        try:
            yield _gemma_explain_result(historial, pregunta, intencion, structured)
        except Exception as e:
            print(f"[OpenRouterError][stream_respuesta][gemma-final] intent={intencion} error={type(e).__name__}: {e}")
            if intencion == INTENCION_RANKING:
                yield _local_ranking_reply(context_data, pregunta)
            elif intencion == INTENCION_RECOMENDACIONES:
                yield _local_recommendations_reply(context_data, pregunta)
            elif intencion == INTENCION_ANALISIS_INDIVIDUAL:
                yield _local_analysis_reply(context_data, pregunta)
            else:
                yield _openrouter_error_message(e, intencion)
        return

    yield _local_chat_reply(pregunta, INTENCION_CONVERSACION)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--reporte":
        print(analisis_automatico())
    else:
        agente_interactivo()


