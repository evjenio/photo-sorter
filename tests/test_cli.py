import shutil

import pytest
from PIL import Image

from photo_sorter.cli import build_parser, main
from photo_sorter.planner import latest_plan


def test_similar_search_is_off_by_default():
    assert build_parser().parse_args(["scan", "src", "dst"]).similar is False


def test_similar_flag_enables_search():
    assert build_parser().parse_args(["scan", "src", "dst", "--similar"]).similar is True


def test_apply_takes_a_plan_path_or_latest_but_not_both():
    parser = build_parser()
    assert parser.parse_args(["apply", "src", "dst", "--latest"]).latest is True
    assert str(parser.parse_args(["apply", "src", "dst", "plan.csv"]).plan) == "plan.csv"
    for argv in (["apply", "src", "dst"], ["apply", "src", "dst", "plan.csv", "--latest"]):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)


def test_latest_plan_is_the_newest_finished_scan(tmp_path):
    plans = tmp_path / ".photo-sorter" / "plans"
    for name in ("20261021-090000", "20261022-101500"):
        (plans / name).mkdir(parents=True)
        (plans / name / "plan.csv").write_text("action\n")
    (plans / "20261022-120000").mkdir()
    assert latest_plan(tmp_path) == plans / "20261022-101500" / "plan.csv"


def test_latest_plan_without_scans_fails_clearly(tmp_path):
    with pytest.raises(SystemExit, match="no plans"):
        latest_plan(tmp_path)


@pytest.mark.skipif(not shutil.which("exiftool"), reason="exiftool is not installed")
def test_run_scans_and_applies_in_one_go(tmp_path):
    source, dest = tmp_path / "source", tmp_path / "dest"
    source.mkdir()
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2024:07:12 10:00:00"
    Image.new("RGB", (8, 8)).save(source / "IMG_0001.JPG", exif=exif)

    assert main(["run", str(source), str(dest), "--workers", "2"]) == 0

    assert (dest / "2024/2024-07/12/2024-07-12_10-00-00.jpg").is_file()
    assert latest_plan(dest).is_file()
