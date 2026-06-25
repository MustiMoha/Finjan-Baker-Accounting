"""UI translation: parallel MyMemory HTTP with optional Argos offline fallback."""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

_MAX_Q_LEN = 500
_CACHE: dict[tuple[str, str, str], str] = {}
_CACHE_LOCK = threading.Lock()
_INSTALLED_PAIRS: set[tuple[str, str]] = set()
_INIT_LOCK = threading.Lock()
_MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_MAX_PARALLEL = 16


def _norm_code(code: str) -> str:
    return (code or "en").strip().lower()[:8] or "en"


def _cache_key(text: str, source: str, target: str) -> tuple[str, str, str]:
    return (_norm_code(source), _norm_code(target), text)


def _prefer_mymemory() -> bool:
    raw = (os.environ.get("BAKER_TRANSLATION_BACKEND") or "mymemory").strip().lower()
    return raw in ("mymemory", "http", "online", "auto", "")


def _ensure_argos_package(from_code: str, to_code: str) -> None:
    """Download and install Argos language pack for ``from_code`` → ``to_code`` if missing."""
    pair = (_norm_code(from_code), _norm_code(to_code))
    if pair in _INSTALLED_PAIRS:
        return
    with _INIT_LOCK:
        if pair in _INSTALLED_PAIRS:
            return
        import argostranslate.package
        import argostranslate.translate

        from_lang = _norm_code(from_code)
        to_lang = _norm_code(to_code)
        installed = argostranslate.translate.get_installed_languages()
        have_from = next((lang for lang in installed if lang.code == from_lang), None)
        have_to = next((lang for lang in installed if lang.code == to_lang), None)
        if have_from and have_to:
            try:
                have_from.get_translation(have_to)
                _INSTALLED_PAIRS.add(pair)
                return
            except Exception:
                pass

        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        package = next(
            (p for p in available if p.from_code == from_lang and p.to_code == to_lang),
            None,
        )
        if package is None:
            raise RuntimeError(
                f"Argos Translate has no package for {from_lang} → {to_lang}. "
                "Supported UI pairs are English ↔ Arabic."
            )
        download_path = package.download()
        argostranslate.package.install_from_path(download_path)
        _INSTALLED_PAIRS.add(pair)


def _argos_translate(text: str, *, source: str, target: str) -> str:
    q = (text or "").strip()
    if not q:
        return text
    if len(q) > _MAX_Q_LEN:
        q = q[:_MAX_Q_LEN]

    _ensure_argos_package(source, target)
    import argostranslate.translate

    from_code = _norm_code(source)
    to_code = _norm_code(target)
    installed = argostranslate.translate.get_installed_languages()
    from_lang = next(lang for lang in installed if lang.code == from_code)
    to_lang = next(lang for lang in installed if lang.code == to_code)
    translation = from_lang.get_translation(to_lang)
    out = translation.translate(q)
    return out.strip() if isinstance(out, str) and out.strip() else text


def _mymemory_translate(text: str, *, source: str, target: str) -> str:
    q = (text or "").strip()
    if not q:
        return text
    if len(q) > _MAX_Q_LEN:
        q = q[:_MAX_Q_LEN]
    src = _norm_code(source)
    tgt = _norm_code(target)
    params = urllib.parse.urlencode({"q": q, "langpair": f"{src}|{tgt}"})
    req = urllib.request.Request(
        f"{_MYMEMORY_URL}?{params}",
        headers={"User-Agent": "Baker/1.0"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload: Any = json.loads(resp.read().decode("utf-8"))
    block = payload.get("responseData") if isinstance(payload, dict) else None
    translated = block.get("translatedText") if isinstance(block, dict) else None
    if not isinstance(translated, str) or not translated.strip():
        raise RuntimeError("MyMemory returned an empty translation.")
    return translated.strip()


def _translate_one(text: str, *, source: str, target: str) -> str:
    src = _norm_code(source)
    tgt = _norm_code(target)
    if src == tgt:
        return text
    key = _cache_key(text, src, tgt)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            return hit

    result = text
    if _prefer_mymemory():
        try:
            result = _mymemory_translate(text, source=src, target=tgt)
        except Exception:
            try:
                result = _argos_translate(text, source=src, target=tgt)
            except Exception:
                result = text
    else:
        try:
            result = _argos_translate(text, source=src, target=tgt)
        except Exception:
            try:
                result = _mymemory_translate(text, source=src, target=tgt)
            except Exception:
                result = text

    with _CACHE_LOCK:
        _CACHE[key] = result
    return result


def translate_text(text: str, *, source: str = "en", target: str = "ar") -> str:
    """Translate one string; uses an in-process cache."""
    return _translate_one(text, source=source, target=target)


def translate_texts(
    texts: list[str],
    *,
    source: str = "en",
    target: str = "ar",
) -> list[str]:
    """Translate many strings in order (parallel for cache misses)."""
    if not texts:
        return []
    src = _norm_code(source)
    tgt = _norm_code(target)
    if src == tgt:
        return list(texts)

    workers = min(_MAX_PARALLEL, max(1, len(texts)))

    def _work(item: tuple[int, object]) -> tuple[int, str]:
        idx, raw = item
        s = str(raw) if raw is not None else ""
        return idx, _translate_one(s, source=src, target=tgt)

    out = [""] * len(texts)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for idx, translated in pool.map(_work, list(enumerate(texts))):
            out[idx] = translated
    return out


def clear_translation_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def reset_translation_packages_for_tests() -> None:
    """Clear caches used by unit tests (does not uninstall Argos packages)."""
    clear_translation_cache()
    _INSTALLED_PAIRS.clear()
