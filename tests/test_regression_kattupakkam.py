"""Regression against the Kattupakkam Site_1 numbers delivered on 2026-10-29 (hand pipeline).
Needs the local database with the 'Kattupakkam Test' site already run (python -m sitesuit.cli run "Kattupakkam Test" ...)."""
import pytest

try:
    from sitesuit import db
    SID = db.site_id("Kattupakkam Test")
except Exception:      # no database here
    SID = None

pytestmark = pytest.mark.skipif(SID is None, reason="local database / Kattupakkam Test site not available")


def test_totals_match_delivery():
    s = db.get_summary(SID)
    assert s["surveys"] == 102 and s["split_surveys"] == 4
    m = s["master"]
    assert abs(m["site_acre"] - 574.05) < 0.02
    assert abs(m["patta_acre"] - 470.97) < 0.02 and abs(m["govt_acre"] - 103.08) < 0.02
    assert abs(m["glv_crore"] - 92.8) < 0.1
    c = s["crop"]
    assert abs(c["crop_acre"] - 180.94) < 0.02 and abs(c["no_survey_acre"] - 104.60) < 0.02
    lc = s["landcost"]["C1"]
    assert abs(lc["act_per_acre"] / 1e5 - 51.50) < 0.05 and abs(lc["neg_per_acre"] / 1e5 - 67.57) < 0.05
