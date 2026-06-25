"""Translation service (Argos Translate)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.translation import (
    clear_translation_cache,
    reset_translation_packages_for_tests,
    translate_text,
    translate_texts,
)


def setup_function() -> None:
    clear_translation_cache()
    reset_translation_packages_for_tests()


def test_translate_text_uses_mymemory_first() -> None:
    with patch("services.translation._mymemory_translate", return_value="مرحبا") as mem:
        with patch("services.translation._argos_translate") as argos:
            out = translate_text("Hello", source="en", target="ar")
    assert out == "مرحبا"
    mem.assert_called_once()
    argos.assert_not_called()


def test_translate_text_falls_back_to_argos() -> None:
    with patch("services.translation._mymemory_translate", side_effect=RuntimeError("offline")):
        with patch("services.translation._argos_translate", return_value="مرحبا") as argos:
            out = translate_text("Hello", source="en", target="ar")
    assert out == "مرحبا"
    argos.assert_called_once()


def test_translate_texts_preserves_order() -> None:
    calls: list[str] = []

    def fake_translate(text: str, *, source: str = "en", target: str = "ar") -> str:
        calls.append(text)
        return f"AR:{text}"

    with patch("services.translation._translate_one", side_effect=fake_translate):
        out = translate_texts(["A", "B", "A"], source="en", target="ar")
    assert out == ["AR:A", "AR:B", "AR:A"]
    assert calls == ["A", "B", "A"]


def test_translate_text_same_language_passthrough() -> None:
    with patch("services.translation._argos_translate") as mock:
        out = translate_text("Hello", source="en", target="en")
    assert out == "Hello"
    mock.assert_not_called()
