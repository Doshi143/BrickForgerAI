import pytest

from brickforge import Model, PartCatalog, Rotation, to_ldr


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_output_has_expected_header_lines(catalog):
    model = Model(catalog=catalog)
    text = to_ldr(model, name="Empty Model", author="Test Author")
    lines = text.splitlines()
    assert lines[0] == "0 Empty Model"
    assert lines[1] == "0 Name: Empty Model.ldr"
    assert lines[2] == "0 Author: Test Author"
    assert "0 BFC CERTIFY CCW" in lines


def test_single_part_line_format(catalog):
    model = Model(catalog=catalog)
    model.place("3005", 4, 0, 0, 0)  # 1x1 brick, red, at origin
    text = to_ldr(model, name="One Brick")
    part_lines = [l for l in text.splitlines() if l.startswith("1 ")]
    assert len(part_lines) == 1
    fields = part_lines[0].split()
    # 1 <color> x y z a b c d e f g h i <file>
    assert len(fields) == 15
    assert fields[0] == "1"
    assert fields[1] == "4"
    assert fields[-1] == "3005.dat"
    # identity matrix for YAW_0
    assert fields[5:14] == ["1", "0", "0", "0", "1", "0", "0", "0", "1"]


def test_part_line_count_matches_model(catalog):
    model = Model(catalog=catalog)
    model.place("3001", 71, 0, 0, 0)  # footprint (4,2): x:[0,4)
    model.place("3001", 71, 4, 0, 0)  # x:[4,8) -- adjacent, not overlapping
    model.place("3024", 15, 0, 3, 0)
    text = to_ldr(model, name="Three Parts")
    part_lines = [l for l in text.splitlines() if l.startswith("1 ")]
    assert len(part_lines) == 3


def test_rotated_part_uses_rotation_matrix(catalog):
    model = Model(catalog=catalog)
    model.place("3001", 71, 0, 0, 0, rotation=Rotation.YAW_90)
    text = to_ldr(model, name="Rotated")
    part_line = [l for l in text.splitlines() if l.startswith("1 ")][0]
    fields = part_line.split()
    assert fields[5:14] == ["0", "0", "1", "0", "1", "0", "-1", "0", "0"]


def test_save_ldr_writes_file(catalog, tmp_path):
    from brickforge import save_ldr

    model = Model(catalog=catalog)
    model.place("3005", 4, 0, 0, 0)
    out_path = tmp_path / "test_model.ldr"
    save_ldr(model, out_path)
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert content.startswith("0 test_model")
