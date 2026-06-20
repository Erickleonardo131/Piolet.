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
MODELO_ACTIVO = MODELOS_GRATUITOS["nemotron-nano"]
MODELO_REPORTE = MODELOS_GRATUITOS["nemotron-nano"]

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

Cuando analices un video específico, SIEMPRE incluye una sección llamada "HISTORIA DEL VIDEO" donde reconstruyas:
- La narrativa o historia que cuenta el video (inicio, desarrollo, desenlace)
- El arco emocional que provoca en el espectador (curiosidad, humor, sorpresa, aspiración, etc.)
- El "gancho" (hook) de los primeros 3 segundos
- El mensaje implícito o subconsciente que transmite la marca
- Por qué esa historia conecta con la audiencia objetivo

Esta sección debe aparecer ANTES de las recomendaciones para Piolet.

Si el usuario pide un reporte, escríbelo siempre en español, con tono profesional y claro.
La sección final debe llamarse "CONCLUSION EJECUTIVA" y debe explicar, en pocas frases, por qué funcionaron los videos observados.
La conclusión debe basarse en señales concretas del contenido: gancho, narrativa, ritmo, duración, formato, tema, audiencia y CTA.
Evita conclusiones genéricas o largas. Prioriza claridad y síntesis.

Responde siempre en español. Sé directo y específico, no genérico.
""".strip()


def get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "Falta la API key de OpenRouter. Configura OPEN_ROUTER_KEY o OPENROUTER_API_KEY en Secrets."
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
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
    except Exception:
        pass
    return fallback


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
            model=MODELO_REPORTE,
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
            model=MODELO_REPORTE,
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


def _detalle_video_nemotron_v2(row: pd.Series) -> str:
    return _detalle_video_descriptivo(row)


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
    df = pd.read_csv(DATA_PATH, index_col="rank")

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
        "Los videos funcionaron porque combinaron un gancho inmediato, una narrativa clara y un formato corto que se consume rapido. "
        "La mezcla de humor, educacion y prueba social elevó el alcance y dio razones concretas para compartir. "
        "Piolet debe replicar esa formula con piezas breves, beneficios especificos y un CTA directo."
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
            "Los videos funcionaron porque mezclan un gancho inmediato con una historia simple y un mensaje que se entiende en segundos. "
            "La combinación de bienestar, educación, prueba social y urgencia comercial da razones concretas para detenerse, mirar y compartir. "
            "Piolet debe replicar esa formula con piezas breves, un beneficio principal por video y un CTA directo."
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
    print(f" AGENTE PIOLET — {MODELO_ACTIVO}")
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

        user_message = (
            f"{pregunta}\n\n[DATOS]\n{context_data}"
            if not historial else pregunta
        )
        historial.append({"role": "user", "content": user_message})

        print("\nAgente: ", end="", flush=True)
        respuesta_completa = ""

        stream = client.chat.completions.create(
            model=MODELO_ACTIVO,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + historial,
            max_tokens=1500,
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


def stream_respuesta(historial: list[dict], pregunta: str, context_data: str):
    """Generador de chunks para st.write_stream en dashboard.py"""
    user_message = (
        f"{pregunta}\n\n[DATOS]\n{context_data}"
        if len(historial) == 0 else pregunta
    )
    mensajes = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + historial
        + [{"role": "user", "content": user_message}]
    )

    # Modelos de razonamiento no soportan streaming en OpenRouter; usar non-stream
    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=MODELO_ACTIVO,
            messages=mensajes,
            max_tokens=4000,
        )
        yield _extraer_contenido(resp.choices[0])
    except Exception:
        yield (
            "No pude consultar el modelo en este momento por un limite temporal del proveedor. "
            "Puedo seguir trabajando con los datos locales cargados en el dashboard."
        )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--reporte":
        print(analisis_automatico())
    else:
        agente_interactivo()


