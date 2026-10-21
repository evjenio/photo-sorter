from photo_sorter.cli import build_parser


def test_similar_search_is_off_by_default():
    assert build_parser().parse_args(["scan", "src", "dst"]).similar is False


def test_similar_flag_enables_search():
    assert build_parser().parse_args(["scan", "src", "dst", "--similar"]).similar is True
