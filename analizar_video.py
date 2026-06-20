import sys, os
sys.path.insert(0, 'C:/Users/erick/OneDrive/Documentos/Escritorio/Piolet')
os.chdir('C:/Users/erick/OneDrive/Documentos/Escritorio/Piolet')
from agent import get_client, SYSTEM_PROMPT, MODELO_ACTIVO, cargar_datos, _extraer_contenido

df, context_data = cargar_datos()

video_info = (
    "VIDEO ANALIZADO:\n"
    "- URL: https://www.instagram.com/p/DRNfpu4klLd/\n"
    "- Cuenta: @plunge (competencia directa en cold plunge/tinas de hielo)\n"
    "- Views: 402,391  |  Likes: 269  |  Comentarios: 4\n"
    "- Duracion: 20 segundos\n"
    "- Caption: Somehow corporate approved this (Black Friday)\n"
    "- Hashtags: #BlackFriday\n"
    "- Tipo: Video / Reel\n\n"
    "CONTEXTO DE MERCADO:\n" + context_data
)

prompt = (
    "Analiza este video de @plunge que obtuvo 402,391 views.\n\n"
    + video_info
    + "\n\nIncluye la seccion HISTORIA DEL VIDEO y despues la conclusion ejecutiva con: "
    "1) por que funciono tan bien, 2) tipo de contenido, "
    "3) que puede aprender Piolet Mexico, 4) idea concreta de video para Piolet."
)

client = get_client()
resp = client.chat.completions.create(
    model=MODELO_ACTIVO,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ],
    max_tokens=4000,
)

os.makedirs("datos", exist_ok=True)
contenido = _extraer_contenido(resp.choices[0]) if resp.choices else resp.model_dump_json(indent=2)
resultado = f"Modelo: {MODELO_ACTIVO}\n{'='*60}\n{contenido}"
with open("datos/analisis_video.txt", "w", encoding="utf-8") as f:
    f.write(resultado)
