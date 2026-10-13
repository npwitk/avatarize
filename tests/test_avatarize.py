import json
import platform
import struct

import pytest

from avatarize import bridge, cli, descriptor

pytestmark = pytest.mark.skipif(platform.system() != "Darwin", reason="needs macOS AvatarKit")


@pytest.fixture(scope="module")
def catalog():
    return bridge.catalog()


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_neutral_is_accepted():
    assert descriptor.rejected_fields(bridge.neutral()) == []


@pytest.mark.parametrize("pick", [0, 1, 5])
def test_every_category_accepts_catalog_values(catalog, pick):
    assignments = []
    for category, entry in catalog.items():
        if entry["presets"]:
            assignments.append(f"{category}={entry['presets'][pick % len(entry['presets'])]['id']}")
        for field, slot in descriptor.COLOR_SLOTS.items():
            if entry["colors"][slot]:
                assignments.append(f"{category}.{field}={entry['colors'][slot][pick % len(entry['colors'][slot])]['name']}")
    desc = descriptor.apply(bridge.neutral(), assignments, catalog)
    # Some presets switch others off (e.g. a hat hides hair styles), so only check most were kept.
    assert len(descriptor.rejected_fields(desc)) < len(assignments) * 0.1


def test_values_match_labels_case_insensitively(catalog):
    desc = descriptor.apply(bridge.neutral(), ["hair.color=auburn", "head.color=Light Fair Skin Tone 2"], catalog)
    assert desc["colors"]["hair"]["name"] == "Auburn"
    assert desc["colors"]["head"]["name"] == "Fitzpatrick 1"


def test_shade_is_clamped_and_kept_when_color_changes(catalog):
    desc = descriptor.apply(bridge.neutral(), ["hair.color=Maple", "hair.shade=3", "hair.color=Auburn"], catalog)
    assert desc["colors"]["hair"] == {"name": "Auburn", "variation": 1.0}


@pytest.mark.parametrize(
    "assignment, message",
    [
        ("hair=curlyy_long", "Did you mean"),
        ("hairr=none", "Did you mean: hair"),
        ("hair.colour=Red", "Unknown field"),
        ("head.shade=dark", "must be a number"),
        ("hair", "Expected key=value"),
    ],
)
def test_bad_assignments_explain_themselves(catalog, assignment, message):
    with pytest.raises(descriptor.AssignmentError, match=message):
        descriptor.apply(bridge.neutral(), [assignment], catalog)


def test_check_reports_values_avatarkit_rejects():
    desc = bridge.neutral()
    desc["presets"]["hair"] = "not_a_hairstyle"
    desc["colors"]["head"] = {"name": "Plaid", "variation": 0}
    assert set(descriptor.rejected_fields(desc)) == {"presets.hair='not_a_hairstyle'", "colors.head='Plaid'"}


def test_poses_include_thumbs_up():
    names = {p["name"]: p for p in bridge.poses()}
    assert names["thumbs_up"]["emoji"] == "👍"
    assert cli.DEFAULT_POSE in names


def test_cli_workflow_renders_square_uncropped_pngs(tmp_path, capsys):
    avatar = tmp_path / "alex.json"
    assert cli.main(["new", str(avatar), "hair=curly_long_upDo_fringe", "hair.color=Auburn"]) == 0
    assert cli.main(["set", str(avatar), "eyewear=rectangle", "eyewear.color=Black"]) == 0
    assert cli.main(["check", str(avatar)]) == 0
    assert json.loads(avatar.read_text())["presets"]["eyewear"] == "rectangle"

    out = tmp_path / "renders"
    assert cli.main(["render", str(avatar), "--pose", "thumbs_up", "--pose", "yearbook", "--out", str(out), "--size", "200"]) == 0
    for pose in ("thumbs_up", "yearbook"):
        png = out / f"alex-{pose}.png"
        assert png_size(png) == (200, 200)
    assert cli.main(["sheet", str(out)]) == 0
    assert "alex-thumbs_up.png" in (out / "index.html").read_text()


def test_cli_rejects_unknown_pose(tmp_path, capsys):
    avatar = tmp_path / "a.json"
    cli.main(["new", str(avatar)])
    assert cli.main(["render", str(avatar), "--pose", "moonwalk"]) == 2
    assert "unknown pose" in capsys.readouterr().err


def test_looks_only_describe_real_values(catalog):
    for category, notes in cli.looks().items():
        assert category in catalog, category
        ids = {p["id"] for p in catalog[category]["presets"]}
        names = {c["name"] for c in catalog[category]["colors"][0]}
        assert set(notes) <= {"about", "presets", "colors"}, category
        assert set(notes.get("presets", {})) <= ids, category
        assert set(notes.get("colors", {})) <= names, category


def test_options_show_looks(capsys):
    assert cli.main(["options", "head"]) == 0
    assert "| looks: widest at the jaw" in capsys.readouterr().out
    assert cli.main(["options", "earrings_right", "--json"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["about"] and next(p for p in entry["presets"] if p["id"] == "roundStud")["looks"]
