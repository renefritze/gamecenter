"""Tests for the pure Buzz! controller report decoder."""

from __future__ import annotations

from gamecenter.input.backends.hidapi_backend import _decode_hid_path, _device_label, decode_buzz_report


def test_short_report_decodes_to_empty():
    assert decode_buzz_report(b"\x00\x00") == ()


def test_no_buttons_pressed():
    state = decode_buzz_report(bytes([0, 0, 0, 0, 0]))
    assert state == tuple([False] * 20)


def test_first_button_bit_sets_first_buzzer_buzz():
    # Bit 0 lives in byte 2; index 0 == buzzer 0, BUZZ button.
    state = decode_buzz_report(bytes([0, 0, 0b0000_0001, 0, 0]))
    assert state[0] is True
    assert not any(state[1:])


def test_high_bits_map_into_later_buzzers():
    # Bit 5 (byte 2) is the start of buzzer 1's buttons (5 buttons per buzzer).
    state = decode_buzz_report(bytes([0, 0, 0b0010_0000, 0, 0]))
    assert state[5] is True


def test_hid_path_decodes_bytes():
    assert _decode_hid_path(b"1-2:1.0") == "1-2:1.0"


def test_device_label_includes_product_and_path():
    assert _device_label({"product_id": 0x1000, "path": b"1-2:1.0"}) == "054c:1000 at 1-2:1.0"
