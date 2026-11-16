"""European region files: written from the Eurostat tables kept in data/eurostat/, never by hand."""
import csv
import hashlib
import json
import os
import subprocess
import sys

import pytest

from branch.builder import build_model, required_factor_keys
from branch.regions import list_regions, load_region

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "experiments", "data"))
import make_eu_regions as eu  # noqa: E402

CAT = "Climate change"
PAIRS = [("pet_bottle_1l", "glass_refillable_1l"), ("aluminium_can_330ml", "beverage_carton_1l")]
CODES = sorted(code for code, _ in eu.COUNTRIES.values())


def synthetic(region):
    keys = required_factor_keys([p for pair in PAIRS for p in pair], region)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: 1.0 + i / 100}} for i, k in enumerate(sorted(set(keys)))}}


def test_the_tables_are_the_ones_read_from_eurostat():
    """Checksums computed in the browser on the Eurostat page on 15 November 2026."""
    want = {"env_waspacr_2022_2024.csv": "04ade28065c8aa19d827987a954cd376b5c0816d98858dc557652fdcf7bcf747",
            "env_wasmun_2022_2024.csv": "3f50efc6ef10c36f88dbea91f496a9f9062e5bfc961730d531471c3160845b7d"}
    for name, digest in want.items():
        with open(os.path.join(ROOT, "data", "eurostat", name), "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == digest, name


def test_the_files_on_disk_are_what_the_tables_give():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "experiments", "data", "make_eu_regions.py"), "--check"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert len(CODES) == 27 and set(CODES) | {"EU"} <= set(list_regions())


def test_the_script_never_writes_the_countries_with_national_sources():
    assert not set(eu.build()) & {"PT", "DE", "BR", "BR-N", "BR-AM", "GLO"}
    for code in ("PT", "DE"):
        assert [r["code"] for r in load_region(code).chain] == [code, "GLO"]


@pytest.mark.parametrize("code", CODES)
def test_every_european_country_builds_and_cites_eurostat(code):
    region = load_region(code)
    assert [r["code"] for r in region.chain] == [code, "EU", "GLO"]
    assert "European Union" not in region.path
    for a, b in PAIRS:
        m = build_model(a, b, code, CAT, synthetic(code))
        for c in m.choices:
            if c.name.endswith((".recycling_rate", ".incineration_share")) and "liquid_packaging_board.recycling" not in c.name:
                assert c.source.startswith("SOURCE: ") and "Eurostat" in c.source, (code, c.name, c.source)
            if c.kind == "continuous" and c.prior[0] == "beta":
                assert c.prior[1]["a"] >= 1 and c.prior[1]["b"] >= 1, (code, c.name, c.prior)


def test_prior_means_follow_the_table():
    """Plastic packaging: the prior mean is the mean of the last two years, within rounding."""
    with open(os.path.join(ROOT, "data", "eurostat", "env_waspacr_2022_2024.csv")) as fh:
        rows = {(r["geo"], r["waste"]): r for r in csv.DictReader(fh) if r["rule"] == "new"}
    for geo, (code, _) in eu.COUNTRIES.items():
        values = [float(rows[(geo, "W150102")][y]) for y in eu.YEARS if rows[(geo, "W150102")][y] != ""][-2:]
        with open(os.path.join(ROOT, "data", "regions", f"{code}.json")) as fh:
            p = json.load(fh)["priors"]["pet.recycling_rate"][1]
        assert abs(p["a"] / (p["a"] + p["b"]) - sum(values) / len(values) / 100) < 0.005, code


def test_the_cases_the_rules_name():
    def prior(code, key):
        with open(os.path.join(ROOT, "data", "regions", f"{code}.json")) as fh:
            return json.load(fh)["priors"][key]
    steel = prior("CY", "steel.recycling_rate")             # reported above 200%
    assert steel[1] == {"a": 19.0, "b": 1.0} and "cut at 95%" in steel[2]
    alu = prior("BG", "aluminium.recycling_rate")           # reported as zero, metals together 63.3%
    assert "reported as zero" in alu[2] and abs(alu[1]["a"] / 12 - 0.633) < 0.005
    assert "only one year" in prior("HU", "pet.recycling_rate")[2]
    glass = prior("FR", "glass.end_of_life")["weights"]
    assert abs(sum(glass.values()) - 1) < 1e-9 and glass["recycling (cut-off)"] == 0.84
    assert load_region("CY").electricity == "electricity_mv_ENTSO-E"   # no national mix in BAFU:2026


def test_the_real_factor_file_has_the_electricity_of_every_european_country():
    path = os.path.join(ROOT, "data", "factors", "bafu2026_EF_3_1_Method_adapted_.json")
    if not os.path.exists(path):
        pytest.skip("needs the factors extracted from BAFU:2026, which are not in the repository")
    with open(path) as fh:
        have = set(json.load(fh)["factors"])
    assert {load_region(c).electricity for c in CODES + ["EU"]} <= have
