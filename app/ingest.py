from pathlib import Path
from functools import lru_cache
from tempfile import TemporaryDirectory
import subprocess
import zipfile
from app.config import settings, TEMP

TEXT_EXTS = {'.txt', '.md', '.log', '.json'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
AUDIO_EXTS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.mpeg', '.mpg'}
SHEET_EXTS = {'.xlsx', '.xls', '.csv'}
SUPPORTED_EXTS = TEXT_EXTS | IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS | SHEET_EXTS | {'.pdf', '.docx'}

class ParseFailure(ValueError):
    pass

def _ocr_image(image):
    import pytesseract
    from app.diagnostics import tesseract_command
    pytesseract.pytesseract.tesseract_cmd = tesseract_command()
    try:
        return pytesseract.image_to_string(image, lang=settings.ocr_languages, timeout=settings.request_timeout_seconds * 3).strip()
    except pytesseract.TesseractError as exc:
        raise ParseFailure('Tesseract could not read the image. Check OCR_LANGUAGES and install the matching traineddata language packs.') from exc
    except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        raise ParseFailure('OCR failed. Install Tesseract and configure TESSERACT_CMD.') from exc

def _pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ParseFailure('Encrypted PDFs must be decrypted before ingestion')
    if len(reader.pages) > settings.max_pdf_pages:
        raise ParseFailure('PDF exceeds MAX_PDF_PAGES')
    sections, ocr_pages, empty_pages = [], [], []
    pdf = None
    try:
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or '').strip()
            ocr = sum(c.isalnum() for c in text) < 20
            if ocr:
                import pypdfium2 as pdfium
                if pdf is None:
                    pdf = pdfium.PdfDocument(str(path))
                rendered = pdf[number - 1]
                try:
                    width, height = rendered.get_size()
                    scale = min(2, 4096 / max(width, height))
                    bitmap = rendered.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        extracted = _ocr_image(image)
                        image.close()
                    finally:
                        bitmap.close()
                    text = extracted or text
                finally:
                    rendered.close()
                ocr_pages.append(number)
            if text:
                sections.append({'text': text, 'page': number, 'ocr': ocr})
            else:
                empty_pages.append(number)
    finally:
        if pdf is not None:
            pdf.close()
    return sections, {'parser': 'pdf', 'pages': len(reader.pages), 'ocr_pages': ocr_pages, 'empty_pages': empty_pages}

def _docx(path):
    from docx import Document
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    doc, sections, heading, table_no = Document(str(path)), [], None, 0
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.style and block.style.name.startswith('Heading'):
                heading = block.text
            if block.text.strip():
                sections.append({'text': block.text, 'heading': heading})
        elif isinstance(block, Table):
            table_no += 1
            for row_no, row in enumerate(block.rows, 1):
                sections.append({'text': ' | '.join(c.text for c in row.cells), 'heading': heading,
                                 'table': table_no, 'row_start': row_no, 'row_end': row_no})
    return sections, {'parser': 'docx', 'tables': table_no}

def _sheet(path):
    import pandas as pd
    if path.suffix.lower() == '.csv':
        sheets = {'CSV': pd.read_csv(path, dtype=str, keep_default_na=False)}
    else:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str, keep_default_na=False)
    sections, counts = [], {}
    for name, frame in sheets.items():
        counts[str(name)] = len(frame)
        columns = [str(c) for c in frame.columns]
        if frame.empty:
            sections.append({'text': 'Columns: ' + ' | '.join(columns), 'sheet': str(name), 'row_start': 1, 'row_end': 1})
        for index, row in enumerate(frame.itertuples(index=False, name=None), 2):
            sections.append({'text': ' | '.join(f'{c}: {v}' for c, v in zip(columns, row)), 'sheet': str(name),
                             'row_start': index, 'row_end': index, 'columns': columns})
    return sections, {'parser': 'spreadsheet', 'sheets': list(counts), 'rows_by_sheet': counts}

@lru_cache(maxsize=1)
def whisper_model():
    from faster_whisper import WhisperModel
    return WhisperModel(settings.whisper_model, device=settings.whisper_device,
                        compute_type=settings.whisper_compute_type, local_files_only=settings.models_local_only)

def _transcribe(path):
    segments, info = whisper_model().transcribe(str(path), vad_filter=True)
    if info.duration > settings.max_media_seconds:
        raise ParseFailure('Media exceeds MAX_MEDIA_SECONDS')
    sections = [{'text': s.text.strip(), 'timestamp_start': float(s.start), 'timestamp_end': float(s.end)}
                for s in segments if s.text.strip()]
    return sections, {'parser': 'audio_whisper', 'language': info.language, 'duration': info.duration}

def _video(path):
    with TemporaryDirectory(prefix='transcribe_', dir=TEMP) as directory:
        wav = Path(directory) / 'audio.wav'
        try:
            subprocess.run([settings.ffmpeg_exe, '-nostdin', '-v', 'error', '-y', '-i', str(path),
                            '-t', str(settings.max_media_seconds + 1), '-vn', '-ac', '1', '-ar', '16000', str(wav)],
                           check=True, capture_output=True, timeout=settings.media_timeout_seconds)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ParseFailure('FFmpeg could not extract audio. Check FFmpeg installation and that the video contains audio.') from exc
        sections, metadata = _transcribe(wav)
        metadata.update(parser='video_whisper', video_audio_extracted=True, visual_understanding=False)
        return sections, metadata

def canonical_text(sections):
    lines = []
    for section in sections:
        meta = {k: v for k, v in section.items() if k != 'text' and v is not None}
        label = ' | '.join(f'{k}: {v}' for k, v in meta.items())
        lines.append((f'[{label}]\n' if label else '') + section['text'])
    return '\n\n'.join(lines)

def parse_file(path):
    suffix = path.suffix.lower()
    if suffix in {'.docx', '.xlsx'}:
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > settings.max_archive_mb * 1024 * 1024:
                raise ParseFailure('Expanded office document exceeds MAX_ARCHIVE_MB')
    if suffix in TEXT_EXTS:
        sections, meta = [{'text': path.read_text(encoding='utf-8-sig', errors='replace')}], {'parser': 'text'}
    elif suffix == '.pdf':
        sections, meta = _pdf(path)
    elif suffix == '.docx':
        sections, meta = _docx(path)
    elif suffix in SHEET_EXTS:
        sections, meta = _sheet(path)
    elif suffix in IMAGE_EXTS:
        from PIL import Image, ImageOps
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original)
            sections, meta = [{'text': _ocr_image(image), 'ocr': True}], {'parser': 'image_ocr', 'width': image.width, 'height': image.height, 'ocr': True}
    elif suffix in AUDIO_EXTS:
        sections, meta = _transcribe(path)
    elif suffix in VIDEO_EXTS:
        sections, meta = _video(path)
    else:
        raise ParseFailure('Unsupported file extension')
    content = canonical_text(sections)
    if len(content) > settings.max_source_chars:
        raise ParseFailure('Extracted text exceeds MAX_SOURCE_CHARS')
    return content, meta, sections
