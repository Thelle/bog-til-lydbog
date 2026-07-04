"""
Tekst -> MP3 via edge-tts (Microsoft neurale stemmer, gratis, online).
Standardstemme: da-DK-JeppeNeural. Retry-logik mod midlertidige netværksfejl.
"""
import asyncio
import edge_tts


async def _synth(text, path, voice):
    for attempt in range(5):
        try:
            await edge_tts.Communicate(text, voice).save(path)
            return
        except Exception as e:
            if attempt < 4:
                wait = 10 * (attempt + 1)
                print(f"    TTS fejl (forsøg {attempt+1}/5): "
                      f"{e.__class__.__name__} — venter {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise


def synth(text, path, voice="da-DK-JeppeNeural"):
    """Gem `text` som MP3 på `path`."""
    asyncio.run(_synth(text, path, voice))
