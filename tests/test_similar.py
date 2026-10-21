import pytest
from PIL import Image, ImageDraw

from photo_sorter.similar import group_similar, perceptual_hash


def test_group_similar_by_bit_distance():
    hashes = {"a": 0xFF00FF00FF00FF00, "b": 0xFF00FF00FF00FF03, "c": 0x00FF00FF00FF00FF}
    assert group_similar(hashes, 2) == [["a", "b"]]
    assert group_similar(hashes, 1) == []


def test_group_similar_rejects_distance_beyond_pigeonhole_bound():
    with pytest.raises(ValueError):
        group_similar({}, 8)


def _picture(path, size, flipped=False):
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 200, 200), fill="red")
    draw.rectangle((220, 120, 380, 280), fill="blue")
    if flipped:
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    image.resize(size).save(path, quality=60)


def test_resized_copy_is_similar_and_different_picture_is_not(tmp_path):
    _picture(tmp_path / "a.jpg", (400, 300))
    _picture(tmp_path / "b.jpg", (200, 150))
    _picture(tmp_path / "c.jpg", (400, 300), flipped=True)
    hashes = {name: perceptual_hash(tmp_path / name) for name in ("a.jpg", "b.jpg", "c.jpg")}
    assert group_similar(hashes, 6) == [["a.jpg", "b.jpg"]]


def test_unreadable_image_has_no_hash(tmp_path):
    (tmp_path / "broken.jpg").write_bytes(b"not an image")
    assert perceptual_hash(tmp_path / "broken.jpg") is None
