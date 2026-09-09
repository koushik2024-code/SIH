"""Plain text exports and deterministic local image + narration composition."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import subprocess
import wave
from contextvars import ContextVar

_video_options = ContextVar("video_options", default={})
from PIL import Image, ImageDraw, ImageFont, ImageOps
from app.config import settings, TEMP, MEDIA_LIBRARY
from app.verify import collect_citations

class RenderFailure(RuntimeError):
    pass

def render_text(data, output_type):
    if output_type == 'linkedin':
        parts = [data['hook'], *data['body'], data['takeaway'], ' '.join(data['hashtags'])]
    elif output_type == 'email':
        parts = ['Subject: ' + data['subject'], data['greeting'], *data['body'], data['call_to_action'], data['sign_off']]
    elif output_type == 'x_post':
        parts = data['posts']
    elif output_type == 'executive_summary':
        parts = [data['title'], data['summary'], '\n'.join('- ' + x for x in data['key_points'])]
    elif output_type == 'advisory':
        parts = [data['title'], ('Severity: ' + data['severity']) if data.get('severity') else '', data['summary'],
                 'Affected: ' + ', '.join(data['affected']), *data['sections'], '\n'.join('- ' + x for x in data['recommendations'])]
    elif output_type == 'infographic':
        parts = [data['title'], 'Infographic content specification', data['headline'], *data['key_points'],
                 'Visual elements: ' + ', '.join(data['visual_elements']), 'Layout: ' + data['layout']]
    elif output_type == 'presentation':
        parts = [f"Slide {i}: {s['title']}\n" + '\n'.join('- ' + b for b in s['bullets']) + '\nSpeaker notes: ' + s['speaker_notes']
                 for i, s in enumerate(data['slides'], 1)]
    else:
        parts = [data['title']] + [f"Scene {s['scene']}: {s['caption']}\n{s['narration']}" for s in data['scenes']]
    return '\n\n'.join(part for part in parts if part)

def save_markdown(data, output_type, path, citation_links=None):
    # Stored exports use stable IDs; links are refreshed by the authenticated download route.
    body = render_text(data, output_type)
    cites = collect_citations(data)
    if cites:
        body += '\n\nSources\n' + '\n'.join(f'- [{c}]({citation_links[c]})' if citation_links and c in citation_links else '- ' + c for c in cites)
    path.write_text(body + '\n', encoding='utf-8')

def _pick_local_image(words):
    tokens = {t.casefold() for word in words for t in re.findall(r'\w+', word) if len(t) > 2}
    best, score = None, 0
    for path in sorted(MEDIA_LIBRARY.rglob('*')):
        if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'} or not path.is_file():
            continue
        if not path.resolve().is_relative_to(MEDIA_LIBRARY.resolve()):
            continue
        tags = path.stem.casefold()
        sidecar = path.with_suffix('.tags.txt')
        if sidecar.is_file() and sidecar.resolve().is_relative_to(MEDIA_LIBRARY.resolve()):
            tags += ' ' + sidecar.read_text(encoding='utf-8')[:4000].casefold()
        matched = sum(t in tags for t in tokens)
        if matched > score:
            best, score = path, matched
    return best

def _font(size):
    for candidate in [_video_options.get().get('font'), settings.video_font, 'C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)

def _wrap(draw, text, font, width):
    lines, current = [], ''
    for char in text:
        if char == '\n' or draw.textlength(current + char, font=font) > width:
            lines.append(current)
            current = '' if char == '\n' else char
        else:
            current += char
    if current:
        lines.append(current)
    return lines

def _scene_image(scene, output):
    options = _video_options.get()
    selected, credit = None, None
    if options.get('web'):
        from app.media import fetch_scene_image
        try:
            credit = fetch_scene_image(scene['visual_keywords'], output, options.get('used'), options.setdefault('warnings', []))
            selected = output if credit else None
        except Exception:
            # Provider/network failure must not abort narration/video generation.
            options.setdefault('warnings', []).append('Internet image lookup failed; used local media or caption cards.')
    if not selected:
        selected = _pick_local_image(scene['visual_keywords'])
    image = Image.new('RGB', (1280, 720), '#10233d')
    if selected:
        try:
            with Image.open(selected) as media:
                image.paste(ImageOps.pad(media.convert('RGB'), (1280, 450), color='#10233d'))
        except (OSError, ValueError):
            selected = None
    draw = ImageDraw.Draw(image)
    if not selected:
        options.setdefault('warnings', []).append(f"Scene {scene['scene']}: no image available; illustrated caption card used.")
        for x, y, radius in [(980, 190, 150), (820, 300, 85), (1100, 350, 60)]:
            draw.ellipse((x-radius,y-radius,x+radius,y+radius), fill='#234b68', outline='#52d6b2', width=4)
        draw.text((64, 150), 'SOURCE BRIEFING', fill='#52d6b2', font=_font(44))
        for i, line in enumerate(_wrap(draw, ' / '.join(scene['visual_keywords']), _font(28), 620)[:4]):
            draw.text((64, 230+i*38), line, fill='white', font=_font(28))
        draw.text((64, 407), 'Illustrated card • no external image available', fill='white', font=_font(20))
    draw.rectangle((0, 450, 1280, 720), fill='#10233d')
    draw.rectangle((64, 482, 130, 488), fill='#52d6b2')
    draw.text((64, 35), f"BRIEFING / {scene['scene']:02d}", fill='white', font=_font(24))
    font = _font(38)
    lines = _wrap(draw, scene['caption'], font, 1150)
    if len(lines) > 4:
        font = _font(28)
        lines = _wrap(draw, scene['caption'], font, 1150)
    for i, line in enumerate(lines):
        draw.text((64, 507 + i * (font.size + 6)), line, fill='white', font=font)
    if credit:
        source_short = credit.get('credit_url', credit['source_url'])
        attribution = (f"Illustrative image: {credit['title']} | {credit['creator']} | {credit['license']} | "
                       f"{source_short} | {credit['license_url']} | Resized, padded, caption added")
        credit_font = _font(14)
        credit_lines = _wrap(draw, attribution, credit_font, 1150)
        draw.rectangle((0, 450 - len(credit_lines)*18 - 16, 1280, 450), fill='#10233d')
        for i, line in enumerate(credit_lines):
            draw.text((64, 450 - len(credit_lines)*18 - 8 + i*18), line, fill='white', font=credit_font)
    image.save(output)
    return credit or {'provider': 'local' if selected else 'caption_card',
                      'name': selected.name if selected else 'generated_caption_card', 'illustrative': True}


def _run(command, input_bytes=None):
    try:
        subprocess.run(command, input=input_bytes, check=True, capture_output=True, timeout=settings.media_timeout_seconds)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RenderFailure('Local media process failed. Check Piper/FFmpeg configuration and voice model.') from exc

def _tts(text, wav):
    from app.diagnostics import video_setup_errors, piper_command
    from app.config import resolve_path
    errors = video_setup_errors(str(_video_options.get().get('voice') or ''))
    if errors:
        raise RenderFailure(' '.join(errors))
    _run([*piper_command(), '-m', str(_video_options.get().get('voice') or resolve_path(settings.piper_model)), '-f', str(wav)], text.encode('utf-8'))

def _dur(path):
    with wave.open(str(path), 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
    if duration <= 0 or duration > 300:
        raise RenderFailure('Narration duration must be between 0 and 300 seconds per scene')
    return duration

def make_video(data, output_path, controls=None):
    from app.languages import voice_for, language_code
    controls = controls or {}
    # Legacy low-level callers/tests may omit controls; API always supplies them.
    try:
        voice = voice_for(controls.get('language', 'English')) if controls else None
    except ValueError as exc:
        raise RenderFailure(str(exc)) from None
    options = {'voice': voice, 'web': bool(controls) and settings.enable_web_images
               and controls.get('image_mode', 'auto') == 'auto' and controls.get('content_scope', 'public') == 'public',
               'font': settings.video_fonts.get(language_code(controls.get('language', 'English'))),
               'used': set(), 'warnings': []}
    context_token = _video_options.set(options)
    timeline = []
    import zipfile
    frames_path = output_path.with_suffix('.frames.zip')
    try:
        with TemporaryDirectory(prefix='video_', dir=TEMP) as directory:
            work = Path(directory)
            segments, start = [], 0.0
            for i, scene in enumerate(data['scenes'], 1):
                png, wav, mp4 = (work / f'scene_{i:02d}.{ext}' for ext in ('png', 'wav', 'mp4'))
                media = _scene_image(scene, png)
                with zipfile.ZipFile(frames_path, 'w' if i == 1 else 'a', zipfile.ZIP_DEFLATED) as archive:
                    archive.write(png, png.name)
                _tts(scene['narration'], wav)
                duration = _dur(wav)
                _run([settings.ffmpeg_exe, '-nostdin', '-v', 'error', '-y', '-loop', '1', '-framerate', '30', '-i', str(png),
                      '-i', str(wav), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage',
                      '-c:a', 'aac', '-ar', '48000', '-ac', '1', '-pix_fmt', 'yuv420p',
                      '-t', f'{duration:.9f}', '-shortest', '-movflags', '+faststart', str(mp4)])
                segments.append(mp4)
                timeline.append({'scene': i, 'start': start, 'duration_seconds': duration, 'media': media,
                                 'caption': scene['caption'], 'citations': scene['citations']})
                start += duration
            concat = work / 'concat.txt'
            # Relative generated filenames avoid quoting problems in Windows/user paths.
            concat.write_text('\n'.join(f"file '{p.name}'" for p in segments), encoding='utf-8')
            _run([settings.ffmpeg_exe, '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', str(concat),
                  '-c', 'copy', '-movflags', '+faststart', str(output_path)])
        output_path.with_suffix('.timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding='utf-8')
        with zipfile.ZipFile(frames_path, 'a', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('timeline.json', json.dumps(timeline, ensure_ascii=False, indent=2))
        return {'scenes': timeline, 'narration_duration_seconds': sum(t['duration_seconds'] for t in timeline),
                'image_warnings': list(dict.fromkeys(options['warnings'])),
                'timing_note': 'Scene target durations use measured WAV length. Encoded MP4 duration is quantized to video frames/audio packets.'}
    except Exception:
        output_path.unlink(missing_ok=True)
        frames_path.unlink(missing_ok=True)
        raise
    finally:
        _video_options.reset(context_token)
