from sitesuit.util import child_of, glv_pick, norm_name, safe_sub, survey_sort_key, utm_epsg, vcode, split_vcode
from sitesuit.geometry import strip_split, split_components
from shapely.geometry import box, MultiPolygon


def test_child_of():
    assert child_of("1A2", "1A") and child_of("1A2", "1")
    assert not child_of("10", "1")          # a number is never cut in half
    assert not child_of("1A", "1A") and not child_of("2", "-")


def test_safe_sub_keeps_text():
    assert safe_sub("2E4") == "2E4" and safe_sub("3.0") == "3" and safe_sub(None) == "-" and safe_sub(float("nan")) == "-"


def test_vcode_letters():
    assert vcode(37, 12, 63) == "37_12_063" and vcode("1", "6", "16A") == "01_06_16A"
    assert split_vcode("37_12_063") == (37, 12, 63)


def test_utm():
    assert utm_epsg(77.5) == 32643 and utm_epsg(79.5) == 32644


def test_sort_key():
    assert sorted(["10", "2", "2A", "100"], key=survey_sort_key) == ["2", "2A", "10", "100"]


def test_glv_rules():
    listed = [(250000, "Acre", "Wet", "d"), (81, "Square Feet", "Res I", "d"), (90, "Square Feet", "Res I", "d")]
    assert glv_pick(listed, 300, False)[1:3] == (81, "Square Feet")      # small plot -> lowest sq-ft rate
    assert glv_pick(listed, 5000, False)[1:3] == (250000, "Acre")        # field -> lowest acre rate
    assert glv_pick(listed, 5000, True)[1] == 0.0                        # govt land -> 0
    assert glv_pick([(81, "Square Feet", "R", "d")], 5000, False)[1:3] == (81, "Square Feet")
    assert glv_pick([], 100, False) is None


def test_norm_name():
    assert norm_name("Perungalathur") == norm_name("Perungalathur ")
    assert norm_name("Kattuppakkam") == norm_name("Kattupakkam")


def test_strip_split_areas():
    p = box(0, 0, 100, 20)
    parts = strip_split(p, [1, 3])
    assert abs(parts[0].area - 500) < 5 and abs(parts[1].area - 1500) < 5


def test_split_components_no_loss():
    reg = MultiPolygon([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    out = split_components(reg, [1, 1, 1])
    assert abs(sum(g.area for g in out) - 200) < 1


def test_dependents_crop_only_touches_maps_and_ppt():
    from sitesuit.pipeline import dependents
    dc = dependents("crop")
    assert {"maps", "ppt"} <= dc and not dc & {"clip", "areg", "glv", "master", "landcost", "fmb"}
    assert dependents("parcels") >= {"clip", "areg", "glv", "master", "crop", "landcost", "fmb", "maps", "ppt"}
    assert "fmb" not in dependents("glv")


def test_company_detection_on_tamil_owner_names():
    from sitesuit.stages.companies import kind
    assert kind("ஸ்பிரிட் ரியல்டார்ஸ் பிரைவேட் லிமிடெட்") == ("Company", "Realtors")
    assert kind("கிரேட் லேக் பிரமோட்டர்ஸ் அண்டு ரியல்டார்ஸ் பி லி")[0] == "Company"
    assert kind("பின்ஜரபோல் டிரஸ்ட் சென்னை") == ("Institution", "Trust")
    assert kind("ஆர்ச் பிஷப் மதராஸ் டயோசிஸ்") == ("Institution", "Diocese / church")
    assert kind("ராஜதுரை நாடார் மகன் ஆர்கஜேந்திரன்") == (None, None)
