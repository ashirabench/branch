"""Web app logic without a browser: form -> specs -> session -> reports."""
import os
import re

import pytest

from branch import interview, webapp


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.delenv("BRANCH_FACTORS", raising=False)
    monkeypatch.setenv("BRANCH_DEMO", "1")


def test_no_factors_no_start(monkeypatch):

    def no_file(*args, **kwargs):          # as on a computer with no file in data/factors/
        raise FileNotFoundError("no factor file")
    monkeypatch.setattr(interview, "load_factors", no_file)
    monkeypatch.delenv("BRANCH_DEMO")
    with pytest.raises(RuntimeError, match="No impact factors"):
        webapp.load_server_factors()


def test_regions_and_templates_are_offered():
    codes = {c for _, c in webapp.available_regions()}
    assert {"PT", "DE", "BR", "BR-N", "BR-AM"} <= codes and "GLO" not in codes
    assert {"PET single use", "Refillable glass", "Aluminium can 330 ml", "Beverage carton 1 L"} <= set(
        webapp.templates())


def test_form_validation_speaks_plainly():
    with pytest.raises(ValueError, match="unknown material"):
        webapp.spec_from_fields("X", 1, False, [["body", "wood", 10]])
    with pytest.raises(ValueError, match="number of grams"):
        webapp.spec_from_fields("X", 1, False, [["body", "pet", "heavy"]])
    with pytest.raises(ValueError, match="at least one component"):
        webapp.spec_from_fields("X", 1, False, [])
    spec = webapp.spec_from_fields("My bottle", 0.5, True, [["Body", "PET", "30,5"], ["cap", "hdpe", 2]])
    assert spec["components"][0] == {"id": "body", "material": "pet", "mass_g": 30.5}


def test_full_session_produces_both_reports(tmp_path):
    factors, is_demo = webapp.load_server_factors()
    assert is_demo
    a = webapp.spec_from_fields(*webapp.template_fields("Refillable glass"))
    b = webapp.spec_from_fields(*webapp.template_fields("PET single use"), used_ids={a["id"]})
    s = webapp.start_session("DE", a, b, factors, public=True, n_samples=5000)
    n = 0
    while not (v := webapp.question_view(s))["done"]:
        raw = v["options"][0] if v["kind"] == "categorical" else v["default"]
        s.answer(v["name"], None if n == 1 else webapp.parse_answer(s, v["name"], raw))
        n += 1
    summary, pdf, md = webapp.finish(s, outdir=str(tmp_path))
    assert os.path.getsize(pdf) > 10_000 and "ISO 14044" in summary
    assert "What would reverse the verdict" in open(md).read()


def test_finish_now_closes_the_session_on_the_defaults(tmp_path):
    factors, _ = webapp.load_server_factors()
    a = webapp.spec_from_fields(*webapp.template_fields("Refillable glass"))
    b = webapp.spec_from_fields(*webapp.template_fields("PET single use"), used_ids={a["id"]})
    s = webapp.start_session("PT", a, b, factors, n_samples=3000)
    v = webapp.question_view(s)
    assert not v["done"]
    s.answer(v["name"], None)                      # one skip, then the person gives up
    s.finish_early()
    assert webapp.question_view(s)["done"]
    r = s.result()
    assert r["questions"] == 1 and isinstance(r["certified"], bool)
    assert all(not who.startswith("human") or "don't know" in who for who in r["decided_by"].values())
    summary, pdf, md = webapp.finish(s, outdir=str(tmp_path))
    assert os.path.getsize(pdf) > 10_000
    assert ("Not settled yet" in summary) == (not r["certified"])


def test_two_skips_in_a_row_suggest_finishing():
    factors, _ = webapp.load_server_factors()
    a = webapp.spec_from_fields(*webapp.template_fields("Refillable glass"))
    b = webapp.spec_from_fields(*webapp.template_fields("PET single use"), used_ids={a["id"]})
    s = webapp.start_session("DE", a, b, factors, n_samples=3000)
    flags = []
    for _ in range(3):
        v = webapp.question_view(s)
        if v["done"]:
            break
        flags.append(webapp.record_answer(s, v["name"], None))
    assert flags[:2] == [False, True]              # the hint comes at the second skip in a row
    v = webapp.question_view(s)
    if not v["done"]:
        raw = v["options"][0] if v["kind"] == "categorical" else v["default"]
        assert webapp.record_answer(s, v["name"], webapp.parse_answer(s, v["name"], raw)) is False
    assert "Finish now" in webapp.UNKNOWN_HINT


def test_answers_outside_the_possible_range_are_refused():
    factors, _ = webapp.load_server_factors()
    a = webapp.spec_from_fields(*webapp.template_fields("Refillable glass"))
    b = webapp.spec_from_fields(*webapp.template_fields("PET single use"), used_ids={a["id"]})
    s = webapp.start_session("PT", a, b, factors, n_samples=3000)
    c = next(c for c in s.model.choices if c.name.endswith("recycling_rate"))
    with pytest.raises(ValueError, match="outside"):
        webapp.parse_answer(s, c.name, "170")
    assert webapp.parse_answer(s, c.name, "") is None


def test_the_page_builds_and_offers_the_entry_points_the_checks_call():
    """The page is laid out by a dozen functions; an error in any of them shows only when the page is built.
    Its entry points are a contract: packaging/smoke_session.py (run on every installer) and
    experiments/openlca/check_app_with_openlca.py call them by these names."""
    pytest.importorskip("gradio")
    offered = set(webapp.build_ui().get_api_info()["named_endpoints"])
    assert {"/on_start", "/answer", "/skip", "/on_finish", "/on_find", "/on_send", "/on_check", "/on_read"} <= offered
    root = os.path.join(os.path.dirname(__file__), "..")
    for script in (("packaging", "smoke_session.py"), ("experiments", "openlca", "check_app_with_openlca.py")):
        called = set(re.findall(r'api_name="(/\w+)"', open(os.path.join(root, *script)).read()))
        assert called and called <= offered, f"{script[-1]} calls {sorted(called - offered)}, which the page does not offer"


def test_every_question_has_plain_help_and_shares_are_in_percent():
    from branch import help as qhelp
    factors, _ = webapp.load_server_factors()
    for region in ("PT", "DE", "BR-AM"):
        for x, y in (("Refillable glass", "PET single use"), ("Aluminium can 330 ml", "Beverage carton 1 L")):
            a = webapp.spec_from_fields(*webapp.template_fields(x))
            b = webapp.spec_from_fields(*webapp.template_fields(y), used_ids={a["id"]})
            s = webapp.start_session(region, a, b, factors, n_samples=2000)
            for c in s.model.choices:
                assert qhelp.help_for(c.name), f"no help for {c.name}"
    c = next(c for c in s.model.choices if c.name.endswith("recycling_rate"))
    assert webapp.parse_answer(s, c.name, "40%") == pytest.approx(0.40)
    assert webapp.parse_answer(s, c.name, "40") == pytest.approx(0.40)
    s.next_question = lambda: c.name
    v = webapp.question_view(s)
    assert v["percent"] and "(%)" in v["text"] and v["range"][1] > 1


def test_every_country_with_a_grid_in_the_factors_can_be_chosen():
    import copy
    factors, _ = webapp.load_server_factors()
    f = copy.deepcopy(factors)
    f["factors"]["electricity_mv_FR"] = dict(f["factors"]["electricity_mv_DE"], location="France")
    regions = dict((c, l) for l, c in webapp.available_regions(f))
    assert regions["FR"] == "France" and "PT" in regions and "BR-AM" in regions
    a = webapp.spec_from_fields(*webapp.template_fields("Refillable glass"))
    b = webapp.spec_from_fields(*webapp.template_fields("PET single use"), used_ids={a["id"]})
    s = webapp.start_session("FR", a, b, f, n_samples=2000)
    assert s.model.meta["region"] == "France"


def test_country_list_is_countries_then_subregions_then_multi_country_grids():
    import copy
    factors, _ = webapp.load_server_factors()
    f = copy.deepcopy(factors)
    base = f["factors"]["electricity_mv_DE"]
    for c, loc in [("AT", "Austria"), ("ENTSOE", "Europe, European Network of Transmission Systems "
                   "Operators for Electricity"), ("US", "United States"),
                   ("US-NPCC", "United States, Northeast Power Coordinating Council")]:
        f["factors"][f"electricity_mv_{c}"] = dict(base, location=loc)
    labels = [l for l, _ in webapp.available_regions(f)]
    assert labels[0] == "Austria" and labels[-1].startswith("Region: Europe")
    assert labels.index("United States > Northeast Power Coordinating Council") == labels.index("United States") + 1
    assert labels.index("Brazil > Northern Brazil") == labels.index("Brazil") + 1
    a = webapp.spec_from_fields(*webapp.template_fields("Refillable glass"))
    b = webapp.spec_from_fields(*webapp.template_fields("PET single use"), used_ids={a["id"]})
    webapp.start_session("ENTSOE", a, b, f, n_samples=1000)


def test_connector_reports_a_closed_openlca_in_plain_words(tmp_path, monkeypatch):
    from branch import connector
    monkeypatch.setenv("BRANCH_HOME", str(tmp_path))
    ready, msg = connector.status(port=1)          # nothing listens on port 1
    assert not ready and "IPC Server" in msg
    assert connector.factors_dir().startswith(str(tmp_path))


def test_connection_panel_lists_four_steps_and_names_the_next_one():
    from branch import connector
    closed = {"port": False, "processes": 0, "method": False, "marker": False}
    steps = connector.checklist(state=closed, factors=False)
    assert [done for done, _, _ in steps] == [False, False, False, False]
    text = connector.checklist_markdown(state=closed, factors=False)
    assert text.count("do this now") == 1 and "1. " in text and "IPC Server" in text

    other_db = {"port": True, "processes": 500, "method": True, "marker": False}
    steps = connector.checklist(state=other_db, factors=False)
    assert [done for done, _, _ in steps] == [True, True, False, False]
    assert "BAFU:2026" in connector.checklist_markdown(state=other_db, factors=False)

    ready = {"port": True, "processes": 500, "method": True, "marker": True}
    assert "Read factors" in connector.checklist_markdown(state=ready, factors=False)
    assert "Everything is ready" in connector.checklist_markdown(state=ready, factors=True)
    # factors already on the computer and openLCA closed: the person can still compare
    assert "you can compare now" in connector.checklist_markdown(state=closed, factors=True)


def test_a_later_step_never_counts_as_done_before_an_earlier_one():
    from branch import connector
    odd = {"port": False, "processes": 500, "method": True, "marker": True}
    assert [d for d, _, _ in connector.checklist(state=odd, factors=False)][:3] == [False, False, False]


def test_a_hosted_page_never_reaches_an_openlca_on_the_server(monkeypatch):
    """A visitor of a hosted page must not read or write the database of an openLCA running on the server."""
    from branch import connector
    monkeypatch.setenv("BRANCH_HOSTED", "1")
    monkeypatch.setattr(connector, "port_open", lambda *a, **k: True)     # as if an openLCA were running there
    ready, message = connector.status()
    assert not ready and "never connects to an openLCA" in message
    with pytest.raises(RuntimeError, match="never connects"):
        connector.client()
    assert connector.probe()["port"] is False
