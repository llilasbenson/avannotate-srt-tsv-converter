import csv
import html
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable, Optional

import streamlit as st


st.set_page_config(page_title="SRT to TSV Converter", page_icon="📝", layout="wide")


# ---------- Configuration ----------

NER_MODELS = {
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
    "pt": "pt_core_news_sm",
}

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Español",
    "pt": "Português",
}

PERSON_LABELS = {"PERSON", "PER"}
ORGANIZATION_LABELS = {"ORG"}

TSV_HEADERS = [
    "SRT Sequence Number",
    "Session Title",
    "Start Timestamp (HH:MM:SS)",
    "End Timestamp (HH:MM:SS)",
    "Subtitle Text",
    "People and Organizations",
]

UI_TEXT = {
    "en": {
        "sidebar_title": "Settings",
        "interface_language": "Interface language / Idioma da interface",
        "title": "SRT to TSV Converter",
        "intro": (
            "Upload one or more SRT files and convert them into TSV tables. "
            "Milliseconds are removed from timestamps, session titles are carried forward, "
            "and named entities are extracted from subtitle text."
        ),
        "session_help_title": "SRT session-title format",
        "session_help": """
A session title may appear directly after a cue number:

```text
1 Opening Session
00:00:01,250 --> 00:00:04,800
Welcome to the conference.

2
00:00:05,000 --> 00:00:08,400
Our first speaker is Ana Silva.
```

`Opening Session` is assigned to cue 1 and all following cues until another cue-number line contains a different title.
        """,
        "ner_language": "Subtitle language for named-entity recognition",
        "ner_help": (
            "Choose the language used in the subtitle text. This setting is independent "
            "of the interface language."
        ),
        "ner_note": (
            "NER results require review. Person names are inverted heuristically to "
            "Family name, Given name; organizations remain in their detected form."
        ),
        "mode_label": "Conversion options",
        "simple_mode": "Simple conversion to TSV",
        "merged_mode": "Convert and merge consecutive lines by speaker (character-based blocks)",
        "merge_help_title": "Speaker detection and merging",
        "merge_help": """
In merging mode, the app preserves the original speaker-detection behavior:

- Text after the end timestamp is treated as an explicit speaker name.
- A subtitle beginning with `-`, `–`, or `—` starts a new unnamed speaker turn.
- A cue without either marker continues the previous speaker.
- Cues are never merged across different session titles.

Merged rows list all contributing sequence numbers as a range when contiguous, or as comma-separated values otherwise. A single unusually long cue may exceed the selected maximum.
        """,
        "target_chars": "Target characters per subtitle block",
        "target_help": "The converter will try to keep merged blocks around this length.",
        "max_chars": "Maximum characters per subtitle block",
        "max_help": "Merged blocks will not exceed this length unless one original cue is already longer.",
        "uploader": "Choose one or more .srt files",
        "spinner_model": "Loading the named-entity recognition model...",
        "spinner_processing": "Processing uploaded files...",
        "missing_model": "The required spaCy language model is not installed.",
        "install_intro": "Install the model in the same Python environment with:",
        "decode_error": "Could not decode {filename} as UTF-8.",
        "no_cues": "No valid SRT cues were found in {filename}.",
        "preview": "Preview of TSV output for {filename} (first 20 lines)",
        "download_one": "Download TSV for {filename}",
        "download_all": "Download all TSV files as ZIP",
        "no_results": "No TSV files were created.",
        "processed_summary": "Processed {files} file(s) and {rows} TSV row(s).",
    },
    "es": {
        "sidebar_title": "Configuración",
        "interface_language": "Idioma de la interfaz / Interface language",
        "title": "Convertidor de SRT a TSV",
        "intro": (
            "Suba uno o más archivos SRT y conviértalos en tablas TSV. "
            "Se eliminan los milisegundos de las marcas de tiempo, se conservan los títulos "
            "de sesión y se extraen entidades nombradas del texto de los subtítulos."
        ),
        "session_help_title": "Formato del título de sesión en el SRT",
        "session_help": """
Un título de sesión puede aparecer directamente después del número de secuencia:

```text
1 Sesión inaugural
00:00:01,250 --> 00:00:04,800
Bienvenidos al congreso.

2
00:00:05,000 --> 00:00:08,400
Nuestra primera ponente es Ana Silva.
```

`Sesión inaugural` se asigna a la secuencia 1 y a las siguientes hasta que otra línea de número de secuencia contenga un título diferente.
        """,
        "ner_language": "Idioma de los subtítulos para el reconocimiento de entidades",
        "ner_help": (
            "Seleccione el idioma del texto de los subtítulos. Esta opción es independiente "
            "del idioma de la interfaz."
        ),
        "ner_note": (
            "Los resultados del reconocimiento de entidades requieren revisión. Los nombres "
            "de personas se invierten de manera heurística a Apellido, Nombre; las organizaciones "
            "se conservan en la forma detectada."
        ),
        "mode_label": "Opciones de conversión",
        "simple_mode": "Conversión simple a TSV",
        "merged_mode": "Convertir y unir líneas consecutivas por hablante (bloques por caracteres)",
        "merge_help_title": "Detección de hablantes y unión",
        "merge_help": """
En el modo de unión, la aplicación conserva el comportamiento original de detección de hablantes:

- El texto después de la marca de tiempo final se interpreta como nombre explícito del hablante.
- Un subtítulo que comienza con `-`, `–` o `—` inicia un nuevo turno de hablante sin nombre.
- Una secuencia sin ninguno de esos indicadores continúa con el hablante anterior.
- Nunca se unen secuencias de distintas sesiones.

Las filas unidas muestran todos los números de secuencia correspondientes como un rango si son consecutivos o separados por comas si no lo son. Una secuencia individual demasiado larga puede superar el máximo seleccionado.
        """,
        "target_chars": "Número objetivo de caracteres por bloque de subtítulos",
        "target_help": "El convertidor intentará mantener los bloques unidos cerca de esta extensión.",
        "max_chars": "Número máximo de caracteres por bloque de subtítulos",
        "max_help": "Los bloques unidos no superarán esta extensión, salvo que una secuencia original ya sea más larga.",
        "uploader": "Seleccione uno o más archivos .srt",
        "spinner_model": "Cargando el modelo de reconocimiento de entidades...",
        "spinner_processing": "Procesando los archivos subidos...",
        "missing_model": "No está instalado el modelo de idioma de spaCy requerido.",
        "install_intro": "Instale el modelo en el mismo entorno de Python con:",
        "decode_error": "No se pudo decodificar {filename} como UTF-8.",
        "no_cues": "No se encontraron secuencias SRT válidas en {filename}.",
        "preview": "Vista previa del TSV de {filename} (primeras 20 líneas)",
        "download_one": "Descargar el TSV de {filename}",
        "download_all": "Descargar todos los archivos TSV como ZIP",
        "no_results": "No se creó ningún archivo TSV.",
        "processed_summary": "Se procesaron {files} archivo(s) y {rows} fila(s) TSV.",
    },
    "pt": {
        "sidebar_title": "Configurações",
        "interface_language": "Idioma da interface / Interface language",
        "title": "Conversor de SRT para TSV",
        "intro": (
            "Envie um ou mais arquivos SRT e converta-os em tabelas TSV. "
            "Os milissegundos são removidos dos tempos, os títulos das sessões são mantidos "
            "e as entidades nomeadas são extraídas do texto das legendas."
        ),
        "session_help_title": "Formato do título da sessão no SRT",
        "session_help": """
Um título de sessão pode aparecer diretamente depois do número da sequência:

```text
1 Sessão de abertura
00:00:01,250 --> 00:00:04,800
Bem-vindos ao congresso.

2
00:00:05,000 --> 00:00:08,400
Nossa primeira palestrante é Ana Silva.
```

`Sessão de abertura` é atribuído à sequência 1 e às sequências seguintes até que outra linha de número de sequência contenha um título diferente.
        """,
        "ner_language": "Idioma das legendas para o reconhecimento de entidades",
        "ner_help": (
            "Selecione o idioma usado no texto das legendas. Esta opção é independente "
            "do idioma da interface."
        ),
        "ner_note": (
            "Os resultados do reconhecimento de entidades precisam ser revisados. Os nomes "
            "de pessoas são invertidos de forma heurística para Sobrenome, Nome; as organizações "
            "permanecem na forma detectada."
        ),
        "mode_label": "Opções de conversão",
        "simple_mode": "Conversão simples para TSV",
        "merged_mode": "Converter e unir linhas consecutivas por falante (blocos por caracteres)",
        "merge_help_title": "Detecção de falantes e união",
        "merge_help": """
No modo de união, o aplicativo preserva o comportamento original de detecção de falantes:

- O texto depois do tempo final é tratado como nome explícito do falante.
- Uma legenda iniciada por `-`, `–` ou `—` começa um novo turno de falante sem nome.
- Uma sequência sem nenhum desses indicadores continua com o falante anterior.
- Sequências de sessões diferentes nunca são unidas.

As linhas unidas mostram todos os números de sequência correspondentes como um intervalo quando são consecutivos ou separados por vírgulas nos demais casos. Uma sequência individual muito longa pode ultrapassar o máximo selecionado.
        """,
        "target_chars": "Meta de caracteres por bloco de legendas",
        "target_help": "O conversor tentará manter os blocos unidos próximos deste tamanho.",
        "max_chars": "Máximo de caracteres por bloco de legendas",
        "max_help": "Os blocos unidos não ultrapassarão este tamanho, salvo quando uma sequência original já for maior.",
        "uploader": "Escolha um ou mais arquivos .srt",
        "spinner_model": "Carregando o modelo de reconhecimento de entidades...",
        "spinner_processing": "Processando os arquivos enviados...",
        "missing_model": "O modelo de idioma spaCy necessário não está instalado.",
        "install_intro": "Instale o modelo no mesmo ambiente Python com:",
        "decode_error": "Não foi possível decodificar {filename} como UTF-8.",
        "no_cues": "Nenhuma sequência SRT válida foi encontrada em {filename}.",
        "preview": "Prévia do TSV de {filename} (primeiras 20 linhas)",
        "download_one": "Baixar o TSV de {filename}",
        "download_all": "Baixar todos os arquivos TSV como ZIP",
        "no_results": "Nenhum arquivo TSV foi criado.",
        "processed_summary": "Foram processados {files} arquivo(s) e {rows} linha(s) TSV.",
    },
}


# ---------- Data structures ----------

@dataclass(frozen=True)
class SRTCue:
    sequence_number: str
    session_title: str
    start: str
    end: str
    speaker_name: Optional[str]
    text: str


@dataclass(frozen=True)
class SpeakerSegment:
    sequence_number: str
    session_title: str
    start_td: timedelta
    end_td: timedelta
    speaker_label: str
    text: str


@dataclass(frozen=True)
class OutputRecord:
    sequence_numbers: tuple[str, ...]
    session_title: str
    start: str
    end: str
    text: str


# ---------- Time and text helpers ----------

TIME_PATTERN = re.compile(
    r"^\s*(\d{1,3}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(\d{1,3}:\d{2}:\d{2}[,.]\d{1,3})"
    r"(?:\s+(.*?))?\s*$"
)

SEQUENCE_PATTERN = re.compile(r"^\s*(\d+)(?:[\t ]+(.+?))?\s*$")
SRT_SETTING_PATTERN = re.compile(r"\b(?:align|line|position|size|vertical):", re.IGNORECASE)


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").replace("\t", " ").split())


def time_to_hhmmss(time_str: str) -> str:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to HH:MM:SS."""
    return re.split(r"[,.]", time_str.strip(), maxsplit=1)[0]


def hhmmss_to_timedelta(hhmmss: str) -> timedelta:
    hours, minutes, seconds = hhmmss.split(":")
    return timedelta(hours=int(hours), minutes=int(minutes), seconds=int(seconds))


def timedelta_to_hhmmss(value: timedelta) -> str:
    total_seconds = int(value.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def looks_like_cue_start(lines: list[str], index: int) -> bool:
    """Return True when lines[index] is a cue-number line followed by a timecode."""
    if index >= len(lines) or not SEQUENCE_PATTERN.match(lines[index].strip()):
        return False

    next_index = index + 1
    while next_index < len(lines) and not lines[next_index].strip():
        next_index += 1

    return next_index < len(lines) and bool(TIME_PATTERN.match(lines[next_index].strip()))


# ---------- SRT parsing ----------

def parse_srt(file_content: str) -> list[SRTCue]:
    """
    Parse standard SRT cues plus the requested extended cue-number syntax:

        1 Session title
        00:00:01,000 --> 00:00:04,000
        Subtitle text

    A non-empty session title persists until another cue-number line supplies one.
    Optional text after the end timestamp is retained as a speaker name for the
    app's existing speaker-merging mode.
    """
    normalized_content = file_content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized_content.split("\n")

    cues: list[SRTCue] = []
    current_session_title = ""
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        sequence_match = SEQUENCE_PATTERN.match(raw_line.strip())

        if not sequence_match:
            index += 1
            continue

        sequence_number = sequence_match.group(1)
        session_title = normalize_whitespace(sequence_match.group(2) or "")
        if session_title:
            current_session_title = session_title

        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1

        if index >= len(lines):
            break

        time_match = TIME_PATTERN.match(lines[index].strip())
        if not time_match:
            # This numeric line was not actually the beginning of a valid SRT cue.
            continue

        start = time_to_hhmmss(time_match.group(1))
        end = time_to_hhmmss(time_match.group(2))
        trailing_text = normalize_whitespace(time_match.group(3) or "")
        speaker_name = (
            trailing_text
            if trailing_text and not SRT_SETTING_PATTERN.search(trailing_text)
            else None
        )

        index += 1
        text_lines: list[str] = []

        while index < len(lines):
            current_line = lines[index]

            if not current_line.strip():
                index += 1
                break

            # Also supports SRT files that omit blank lines between cues.
            if looks_like_cue_start(lines, index):
                break

            text_lines.append(current_line.strip())
            index += 1

        subtitle_text = normalize_whitespace(" ".join(text_lines))
        cues.append(
            SRTCue(
                sequence_number=sequence_number,
                session_title=current_session_title,
                start=start,
                end=end,
                speaker_name=speaker_name,
                text=subtitle_text,
            )
        )

    return cues


# ---------- Speaker segmentation and merging ----------

def build_speaker_segments(cues: Iterable[SRTCue]) -> list[SpeakerSegment]:
    """Apply the original speaker-detection rules to parsed SRT cues."""
    segments: list[SpeakerSegment] = []
    last_speaker_label: Optional[str] = None
    anonymous_speaker_count = 0

    for cue in cues:
        raw_text = cue.text or ""
        cleaned_text = raw_text.strip()

        if cue.speaker_name:
            speaker_label = cue.speaker_name.strip()
            last_speaker_label = speaker_label
        elif cleaned_text.startswith(("-", "–", "—")):
            anonymous_speaker_count += 1
            speaker_label = f"Speaker {anonymous_speaker_count}"
            cleaned_text = cleaned_text[1:].strip()
            last_speaker_label = speaker_label
        elif last_speaker_label is not None:
            speaker_label = last_speaker_label
        else:
            speaker_label = "Unknown"
            last_speaker_label = speaker_label

        segments.append(
            SpeakerSegment(
                sequence_number=cue.sequence_number,
                session_title=cue.session_title,
                start_td=hhmmss_to_timedelta(cue.start),
                end_td=hhmmss_to_timedelta(cue.end),
                speaker_label=speaker_label,
                text=normalize_whitespace(cleaned_text),
            )
        )

    return segments


def merge_segments_by_speaker(
    segments: Iterable[SpeakerSegment],
    target_chars: int = 250,
    max_chars: int = 300,
) -> list[OutputRecord]:
    """
    Merge consecutive segments from the same speaker and session.

    target_chars is retained for compatibility with the original app. max_chars
    remains the hard merge threshold except when one source cue is already longer.
    """
    segment_list = list(segments)
    if not segment_list:
        return []

    merged: list[OutputRecord] = []
    current_sequences: list[str] = []
    current_session = ""
    current_speaker: Optional[str] = None
    current_start: Optional[timedelta] = None
    current_end: Optional[timedelta] = None
    current_text_parts: list[str] = []

    def flush_current() -> None:
        nonlocal current_sequences, current_session, current_speaker
        nonlocal current_start, current_end, current_text_parts

        if current_speaker is not None and current_start is not None and current_end is not None:
            merged.append(
                OutputRecord(
                    sequence_numbers=tuple(current_sequences),
                    session_title=current_session,
                    start=timedelta_to_hhmmss(current_start),
                    end=timedelta_to_hhmmss(current_end),
                    text=normalize_whitespace(" ".join(current_text_parts)),
                )
            )

        current_sequences = []
        current_session = ""
        current_speaker = None
        current_start = None
        current_end = None
        current_text_parts = []

    for segment in segment_list:
        if current_speaker is None:
            current_sequences = [segment.sequence_number]
            current_session = segment.session_title
            current_speaker = segment.speaker_label
            current_start = segment.start_td
            current_end = segment.end_td
            current_text_parts = [segment.text]
            continue

        speaker_changed = segment.speaker_label != current_speaker
        session_changed = segment.session_title != current_session

        if speaker_changed or session_changed:
            flush_current()
            current_sequences = [segment.sequence_number]
            current_session = segment.session_title
            current_speaker = segment.speaker_label
            current_start = segment.start_td
            current_end = segment.end_td
            current_text_parts = [segment.text]
            continue

        current_text = normalize_whitespace(" ".join(current_text_parts))
        candidate_length = len(current_text) + (1 if current_text and segment.text else 0) + len(segment.text)

        if candidate_length <= max_chars:
            current_sequences.append(segment.sequence_number)
            current_text_parts.append(segment.text)
            current_end = segment.end_td
        else:
            # Flush at the maximum boundary. target_chars is intentionally retained
            # as the desired block size, but the original app also prioritized max_chars.
            _ = target_chars
            flush_current()
            current_sequences = [segment.sequence_number]
            current_session = segment.session_title
            current_speaker = segment.speaker_label
            current_start = segment.start_td
            current_end = segment.end_td
            current_text_parts = [segment.text]

    flush_current()
    return merged


def cues_to_simple_records(cues: Iterable[SRTCue]) -> list[OutputRecord]:
    return [
        OutputRecord(
            sequence_numbers=(cue.sequence_number,),
            session_title=cue.session_title,
            start=cue.start,
            end=cue.end,
            text=cue.text,
        )
        for cue in cues
    ]


def format_sequence_numbers(sequence_numbers: Iterable[str]) -> str:
    values = list(sequence_numbers)
    if not values:
        return ""
    if len(values) == 1:
        return values[0]

    try:
        numbers = [int(value) for value in values]
    except ValueError:
        return ", ".join(values)

    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"{numbers[0]}-{numbers[-1]}"

    return ", ".join(values)


# ---------- Named-entity recognition ----------

@st.cache_resource(show_spinner=False)
def load_ner_model(language_code: str) -> Any:
    import spacy

    model_name = NER_MODELS[language_code]
    nlp = spacy.load(model_name)

    # Keep the NER component and its feature-producing dependency; disable other
    # components to reduce processing time without making assumptions about which
    # optional components are present in each language pipeline.
    keep_components = {"ner", "tok2vec", "transformer"}
    for component_name in list(nlp.pipe_names):
        if component_name not in keep_components:
            nlp.disable_pipe(component_name)

    return nlp


def clean_text_for_ner(text: str) -> str:
    without_ass_tags = re.sub(r"\{\\[^{}]*\}", " ", text or "")
    without_html_tags = re.sub(r"<[^>]+>", " ", without_ass_tags)
    return normalize_whitespace(html.unescape(without_html_tags))


def format_person_name(name: str) -> str:
    """Heuristically invert a detected person name to Family name, Given name."""
    cleaned = normalize_whitespace(name).strip(" ,;:")
    if not cleaned:
        return ""

    # Preserve an entity that the source already presents in inverted form.
    if "," in cleaned:
        family, given = (part.strip() for part in cleaned.split(",", 1))
        return f"{family}, {given}" if given else family

    tokens = cleaned.split()
    honorifics = {
        "mr", "mrs", "ms", "miss", "dr", "prof", "sir", "dame",
        "sr", "sra", "srta", "dr", "dra", "professor", "professora",
        "dom", "dona", "don", "doña",
    }
    while len(tokens) > 1 and tokens[0].casefold().rstrip(".") in honorifics:
        tokens.pop(0)

    if len(tokens) == 1:
        return tokens[0]

    suffixes = {"jr", "sr", "ii", "iii", "iv", "filho", "neto", "júnior", "junior"}
    family_start = len(tokens) - 1
    if tokens[-1].casefold().rstrip(".,") in suffixes and len(tokens) >= 3:
        family_start = len(tokens) - 2

    surname_particles = {
        "da", "das", "de", "del", "della", "der", "di", "do", "dos",
        "du", "la", "las", "le", "los", "van", "von", "y",
    }
    while family_start > 0 and tokens[family_start - 1].casefold().strip(".,") in surname_particles:
        family_start -= 1

    given_names = " ".join(tokens[:family_start]).strip()
    family_names = " ".join(tokens[family_start:]).strip()

    if not given_names:
        return family_names
    return f"{family_names}, {given_names}"


def deduplicate_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        normalized = normalize_whitespace(value)
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)

    return output


def extract_entities_batch(texts: Iterable[str], nlp: Any) -> list[str]:
    cleaned_texts = [clean_text_for_ner(text) for text in texts]
    results: list[str] = []

    for doc in nlp.pipe(cleaned_texts, batch_size=32):
        entities: list[str] = []

        for entity in doc.ents:
            label = entity.label_.upper()
            entity_text = normalize_whitespace(entity.text)

            if label in PERSON_LABELS:
                formatted = format_person_name(entity_text)
                if formatted:
                    entities.append(formatted)
            elif label in ORGANIZATION_LABELS and entity_text:
                entities.append(entity_text)

        results.append(" | ".join(deduplicate_preserving_order(entities)))

    return results


# ---------- TSV generation ----------

def records_to_tsv(records: Iterable[OutputRecord], nlp: Any) -> str:
    record_list = list(records)
    entity_values = extract_entities_batch((record.text for record in record_list), nlp)

    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(TSV_HEADERS)

    for record, entities in zip(record_list, entity_values):
        writer.writerow(
            [
                format_sequence_numbers(record.sequence_numbers),
                normalize_whitespace(record.session_title),
                record.start,
                record.end,
                normalize_whitespace(record.text),
                entities,
            ]
        )

    return output.getvalue()


def convert_srt_to_tsv(
    file_content: str,
    nlp: Any,
    merge_by_speaker: bool = False,
    target_chars: int = 250,
    max_chars: int = 300,
) -> tuple[str, int]:
    cues = parse_srt(file_content)
    if not cues:
        return "", 0

    if merge_by_speaker:
        segments = build_speaker_segments(cues)
        records = merge_segments_by_speaker(
            segments,
            target_chars=target_chars,
            max_chars=max_chars,
        )
    else:
        records = cues_to_simple_records(cues)

    return records_to_tsv(records, nlp), len(records)


# ---------- Streamlit interface ----------

st.sidebar.title("Settings / Configuración / Configurações")
interface_language = st.sidebar.selectbox(
    "Interface language / Idioma de la interfaz / Idioma da interface",
    options=list(LANGUAGE_NAMES),
    format_func=lambda code: LANGUAGE_NAMES[code],
)
T = UI_TEXT[interface_language]

st.sidebar.caption(T["sidebar_title"])

st.title(T["title"])
st.write(T["intro"])

with st.expander(T["session_help_title"], expanded=False):
    st.markdown(T["session_help"])

ner_language = st.selectbox(
    T["ner_language"],
    options=list(LANGUAGE_NAMES),
    index=list(LANGUAGE_NAMES).index(interface_language),
    format_func=lambda code: LANGUAGE_NAMES[code],
    help=T["ner_help"],
)
st.caption(T["ner_note"])

mode = st.radio(
    T["mode_label"],
    options=["simple", "merged"],
    format_func=lambda value: T["simple_mode"] if value == "simple" else T["merged_mode"],
)

with st.expander(T["merge_help_title"], expanded=False):
    st.markdown(T["merge_help"])

if mode == "merged":
    target_chars = st.number_input(
        T["target_chars"],
        min_value=50,
        max_value=2000,
        value=250,
        step=10,
        help=T["target_help"],
    )
    max_chars = st.number_input(
        T["max_chars"],
        min_value=int(target_chars),
        max_value=4000,
        value=max(300, int(target_chars * 1.2)),
        step=10,
        help=T["max_help"],
    )
else:
    target_chars = 250
    max_chars = 300

uploaded_files = st.file_uploader(
    T["uploader"],
    type=["srt", "txt"],
    accept_multiple_files=True,
)

if uploaded_files:
    try:
        with st.spinner(T["spinner_model"]):
            nlp_model = load_ner_model(ner_language)
    except (ImportError, OSError) as error:
        model_name = NER_MODELS[ner_language]
        st.error(f"{T['missing_model']} ({model_name})")
        st.write(T["install_intro"])
        st.code(f"python -m spacy download {model_name}", language="bash")
        st.exception(error)
        st.stop()

    tsv_results: list[tuple[str, str, int]] = []

    with st.spinner(T["spinner_processing"]):
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            try:
                file_text = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                st.error(T["decode_error"].format(filename=uploaded_file.name))
                continue

            tsv_text, row_count = convert_srt_to_tsv(
                file_text,
                nlp=nlp_model,
                merge_by_speaker=(mode == "merged"),
                target_chars=int(target_chars),
                max_chars=int(max_chars),
            )

            if not tsv_text:
                st.warning(T["no_cues"].format(filename=uploaded_file.name))
                continue

            tsv_results.append((uploaded_file.name, tsv_text, row_count))

    if not tsv_results:
        st.error(T["no_results"])
        st.stop()

    total_rows = sum(result[2] for result in tsv_results)
    st.success(T["processed_summary"].format(files=len(tsv_results), rows=total_rows))

    first_name, first_tsv, _ = tsv_results[0]
    st.subheader(T["preview"].format(filename=first_name))
    preview_lines = "\n".join(first_tsv.splitlines()[:20])
    st.text(preview_lines)

    if len(tsv_results) == 1:
        output_name = first_name.rsplit(".", 1)[0] + ".tsv"
        st.download_button(
            label=T["download_one"].format(filename=first_name),
            data=first_tsv.encode("utf-8-sig"),
            file_name=output_name,
            mime="text/tab-separated-values",
        )
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for original_name, tsv_text, _ in tsv_results:
                tsv_name = original_name.rsplit(".", 1)[0] + ".tsv"
                zip_file.writestr(tsv_name, tsv_text.encode("utf-8-sig"))

        zip_buffer.seek(0)
        st.download_button(
            label=T["download_all"],
            data=zip_buffer,
            file_name="converted_srt_tsv_files.zip",
            mime="application/zip",
        )
