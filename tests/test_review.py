"""The review of the repository, as tests.

What a careful reader would check by hand before trusting the repository is checked here on every push:
that a number written by hand in the paper, the README or the claims is the one of the committed data;
that every link and every file named in the documents exists; that the version is the same everywhere;
and that no value of the licensed database is in a tracked file.
"""
import glob
import importlib.util
import json
import os
import re
import subprocess

import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
V02 = os.path.join(ROOT, "paper", "data", "v02_2026-11-16")
TAU = 0.025


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def load(*parts):
    path = os.path.join(ROOT, *parts)
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def block(name, truth, strategy="decision_flip"):
    return pd.read_csv(os.path.join(V02, f"{name}_{truth}.csv")).set_index("strategy").loc[strategy]


def tracked():
    """Files that git tracks; None when this is not a git checkout (an unpacked archive)."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except Exception:
        return None
    return [f for f in out.split("\n") if f]


def documents():
    files = tracked()
    if files is None:
        files = [os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "**", "*.md"), recursive=True)
                 if ".venv" not in p]
    return [f for f in files if f.endswith(".md")]


TEX, README, CLAIMS = read("paper", "main.tex"), read("README.md"), read("docs", "CLAIMS.md")


# ---------------------------------------------------------------- numbers against the data

def test_the_numbers_file_of_the_paper_is_the_one_the_data_give(tmp_path, monkeypatch):
    """paper/tables/numbers.tex is generated. Generating it again from the committed summaries must
    give the committed file, so nobody can edit a number of the paper by hand."""
    assets = load("experiments", "benchmark", "paper_assets.py")
    monkeypatch.setattr(assets, "TABS", str(tmp_path))
    assets.numbers()
    assert (tmp_path / "numbers.tex").read_text(encoding="utf-8") == read("paper", "tables", "numbers.tex")


def test_the_third_ablation_as_written():
    base, part, full = (block(b, "prior") for b in ("cutoff", "uncertainty_consistent", "uncertainty"))
    counts = [int(b.cases_no_question) for b in (base, part, full)]
    more = [f"{b.q_mean - base.q_mean:.2f}" for b in (part, full)]
    open_ = [f"{100 - b.certified_pct:.0f}" for b in (part, full)]
    wrong = [f"{block(b, 'tails').wrong_when_certified_pct:.1f}" for b in ("cutoff", "uncertainty_consistent", "uncertainty")]
    flat = " ".join(TEX.split())
    assert f"{more[0]} (" in flat and f"{more[1]} (" in flat
    assert f"ends {open_[0]}\\% and {open_[1]}\\% of the sessions without a certificate" in flat
    row = next(x for x in CLAIMS.split("\n") if x.startswith("| 17 |"))
    assert f"certifies {counts[1]} of the 18 cases from the priors alone instead of {counts[0]}" in row
    assert f"asks {more[0]} questions more" in row and f"{counts[2]} cases and {more[1]} questions more" in row
    assert f"{open_[0]}% and {open_[1]}% of the sessions" in row
    assert f"({wrong[1]}% and {wrong[2]}% against {wrong[0]}%)" in row
    # the README rounds the same two numbers to one decimal
    assert f"between {float(more[0]):.1f} and {float(more[1]):.1f} more questions" in README


def test_the_interactions_as_written():
    df = pd.read_csv(os.path.join(ROOT, "paper", "data", "interactions_2026-11-17.csv"))
    asks = df[df.p_a_lower.clip(upper=1 - df.p_a_lower) > TAU]     # the agent asks only when it cannot certify
    total = asks.groupby("case").first_order.sum()
    first = three = 0
    for _, d in asks.groupby("case"):
        s = d.sort_values("first_order", ascending=False).choice.tolist()
        t = d.sort_values("total", ascending=False).choice.tolist()
        first += s[0] == t[0]
        three += set(s[:3]) == set(t[:3])
    n = asks.case.nunique()
    assert (f"in the {n} cases where the agent asks, the first order indices of the verdict sum to "
            f"{total.min():.2f}--{total.max():.2f}") in TEX
    assert f"the same first question in {first} of them and the same three in {three}" in TEX
    row = next(x for x in CLAIMS.split("\n") if x.startswith("| 18 |"))
    assert f"In the {n} cases" in row and f"sum to {total.min():.2f} to {total.max():.2f}" in row
    assert f"the same first question in {first} and the same first three in {three}" in row


def test_the_results_table_of_the_readme():
    flip, ent = block("families", "prior"), block("families", "prior", "entropy")
    lo, hi = ent.dq_ci95_pair.split(" to ")
    assert (f"{flip.q_mean:.2f} against {ent.q_mean:.2f} questions on {int(flip.cases)} cases of ten pairs of packages; "
            f"difference {ent.dq_vs_decision_flip:.2f}, 95% interval over pairs {lo} to {hi}, p = {ent.p_pair:.3f}") in README
    eq_f = block("eq_families", "prior", "sobol").dq_vs_decision_flip
    eq_b = block("eq_bench", "prior", "sobol").dq_vs_decision_flip
    assert f"Difference of {abs(eq_f):.2f} question on 30 cases and {abs(eq_b):.2f} on 18" in README
    # wrong certificates with experts that contradict the beliefs: every run of the 18 cases in the chosen setting
    runs = [pd.read_csv(os.path.join(ROOT, "paper", "data", f)).query("strategy == 'decision_flip' and batch_size == 3")
            .wrong_when_certified_pct.iloc[0]
            for f in ("benchmark_tails_tau0.025.csv", "benchmark_tails_tau0.025_confirm.csv",
                      os.path.join("more_seeds_2026-11-16", "climate_change_tails.csv"))]
    runs.append(block("stress_bench", "adverse").wrong_when_certified_pct)
    other = block("families", "tails").wrong_when_certified_pct
    assert (f"{min(runs):.1f}% to {max(runs):.1f}% of the certified verdicts of the 18 beverage cases are wrong against a "
            f"target of {100 * TAU:.1f}%; {other:.1f}% in the 30 other cases") in README
    grids = pd.read_csv(os.path.join(ROOT, "paper", "data", "validation_all_grids.csv"))
    grids = grids[grids["product"].notna() & (grids["product"].astype(str) != "")]
    mant, exp = f"{grids.relative_difference.astype(float).max():.1e}".split("e")
    power = str(int(exp)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
    assert f"{mant} × 10{power} over {len(grids)} products in {grids.region.nunique()} regions" in README
    # the synthetic illustration: the README against the generated summary
    line = next(x for x in read("paper", "data", "v02_2026-11-16", "SUMMARY.md").split("\n") if x.startswith("| 1 | "))
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert f"({cells[4]} fewer, {cells[5]})" in README


def test_what_the_readme_says_it_covers():
    from branch.catalogue import load_materials
    assert f"from {len(load_materials())} materials" in README
    regions = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, "data", "regions", "*.json"))}
    national = {"PT", "DE", "BR"}
    other = {r for r in regions if len(r) == 2 and r not in national | {"EU"}}
    assert len(other - {"IS", "NO"}) == 25 and {"IS", "NO"} <= other, "the README says 25 other EU countries, Iceland and Norway"
    assert {"BR-N", "BR-AM"} <= regions
    from branch.indicators import EF31
    main = {name for _, (name, _) in EF31 if not name.startswith("Climate change, ")}   # the three splits of climate aside
    assert f"all {len(main)} categories of EF 3.1" in README


# ---------------------------------------------------------------- links and files

def anchor(heading):
    """The anchor GitHub gives to a heading."""
    text = re.sub(r"[`*_]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


@pytest.mark.parametrize("doc", documents())
def test_every_link_of_a_document_leads_somewhere(doc):
    text = re.sub(r"```.*?```", "", read(doc), flags=re.S)
    here = os.path.dirname(os.path.join(ROOT, doc))
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"(https?:|mailto:)", target):
            continue
        path, _, frag = target.partition("#")
        full = os.path.normpath(os.path.join(here, path)) if path else os.path.join(ROOT, doc)
        assert os.path.exists(full), f"{doc}: the link {target} leads to nothing"
        if frag and full.endswith(".md"):
            heads = [anchor(h) for h in re.findall(r"^#+ (.+)$", open(full, encoding="utf-8").read(), re.M)]
            assert frag in heads, f"{doc}: no heading #{frag} in {os.path.relpath(full, ROOT)}"


def test_every_file_named_as_evidence_exists():
    """The column Evidence of docs/CLAIMS.md: every path, also a pattern with *, names a tracked file."""
    last = ""
    checked = 0
    for line in CLAIMS.split("\n"):
        cells = line.split("|")
        if len(cells) < 5 or not cells[1].strip().isdigit():
            continue
        for name in re.findall(r"`([^`]+)`", cells[3]):
            if "/" in name:
                last = os.path.dirname(name)
            candidates = [name, os.path.join(last, name), os.path.join("paper", "data", name)]
            assert any(glob.glob(os.path.join(ROOT, c)) for c in candidates), f"claim {cells[1].strip()}: {name} does not exist"
            checked += 1
    assert checked > 20


def test_every_script_named_in_the_documents_exists():
    for doc in documents():
        named = r"((?:experiments|branch|tests|examples|packaging|docs|data|paper)/[\w./\-]+\.(?:py|sh|md|json|csv|tex))"
        for name in re.findall(named, read(doc)):
            if "<" in name or "*" in name or name.startswith("data/factors") or "mydb" in name:
                continue                      # patterns, local files, and the example name of the database guide
            assert os.path.exists(os.path.join(ROOT, name)), f"{doc} names {name}, which does not exist"


def test_the_paper_points_only_to_what_exists():
    paper = os.path.join(ROOT, "paper")
    for name in re.findall(r"\\input\{([^}]+)\}", TEX):
        assert os.path.exists(os.path.join(paper, name if name.endswith(".tex") else name + ".tex")), name
    for name in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", TEX):
        assert glob.glob(os.path.join(paper, name) + "*"), name
    labels = set(re.findall(r"\\label\{([^}]+)\}", TEX))
    for ref in re.findall(r"\\(?:ref|eqref|autoref)\{([^}]+)\}", TEX):
        assert ref in labels, f"\\ref{{{ref}}} has no \\label"
    keys = re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", read("paper", "references.tex"))
    assert len(keys) == len(set(keys)), "a reference appears twice"
    cited = {key.strip() for group in re.findall(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]+)\}", TEX) for key in group.split(",")}
    assert cited <= set(keys), f"cited but not in the references: {sorted(cited - set(keys))}"
    assert set(keys) <= cited, f"in the references but never cited: {sorted(set(keys) - cited)}"
    for name in re.findall(r"\\texttt\{(paper/data/[^}]+)\}", TEX):
        assert glob.glob(os.path.join(ROOT, name.replace("\\_", "_"))), f"the paper names {name}"


def test_the_architecture_page_names_only_what_the_code_has():
    """docs/ARCHITECTURE.md says where each idea of the paper lives. Every file of its tables exists and
    defines every name written beside it, so the page cannot fall behind the code without notice."""
    rows = 0
    for line in read("docs", "ARCHITECTURE.md").split("\n"):
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5 or not re.fullmatch(r"`[\w/]+\.py`", cells[2]):
            continue
        path = cells[2].strip("`")
        assert os.path.exists(os.path.join(ROOT, path)), f"{path} does not exist"
        source = read(path)
        for name in re.findall(r"`([^`]+)`", cells[3]):
            n = re.escape(name)
            assert re.search(rf"(def|class) {n}\b|^\s*{n}\b\s*[:=]|\b{n}=", source, re.M), f"{path} does not define {name}"
        rows += 1
    assert rows > 40


# ---------------------------------------------------------------- one version

def test_one_version_in_every_place_that_states_it():
    import branch
    v = branch.__version__
    assert re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.M).group(1) == v
    assert re.search(r"^version: (\S+)", read("CITATION.cff"), re.M).group(1) == v
    assert re.search(r'^#define Version "([^"]+)"', read("packaging", "windows.iss"), re.M).group(1) == v
    assert re.search(r'"CFBundleShortVersionString": "([^"]+)"', read("packaging", "branch.spec")).group(1) == v
    assert f"Release v{v}" in read("CHANGELOG.md"), "the changelog has no entry for this version"
    assert v in read("packaging", "release_notes.md"), "the text of the release page does not name this version"
    newest = re.search(r"Release v(\d+\.\d+\.\d+)", read("CHANGELOG.md")).group(1)
    assert newest == v, "the newest release of the changelog is not the version of the code"


def test_the_release_command_knows_the_same_places():
    script = read("release.sh")
    for name in ("pyproject.toml", "branch/__init__.py", "CITATION.cff", "packaging/windows.iss", "packaging/branch.spec"):
        assert script.count(f'"{name}"') == 1, name
    assert "\r" not in script
    # the command tests with the packages each run on GitHub installs; the lists must not drift apart
    for workflow, extras in (("tests.yml", '".[dev,experiments,app]"'), ("installers.yml", '".[app,olca,report]"')):
        assert extras in read(".github", "workflows", workflow), workflow
        assert extras in script, extras


# ---------------------------------------------------------------- nothing of the licensed database

FORBIDDEN = re.compile(r"^(results|data/factors|data/factors_second|outputs)/|\.zolca$|(^|/)derby\.log$")


def test_no_file_of_the_database_is_tracked():
    files = tracked()
    if files is None:
        pytest.skip("not a git checkout")
    assert not [f for f in files if FORBIDDEN.search(f)]
    ignore = read(".gitignore").split("\n")
    for rule in ("results/", "data/factors/", "data/factors_second/", "*.zolca", "outputs/"):
        assert rule in ignore, f".gitignore lost the rule {rule}"


def test_no_value_of_the_database_is_in_a_tracked_file():
    """With the factor file on this computer: none of its numbers appears, to ten significant digits, in
    any tracked text file. Without the file (GitHub, a fresh clone) there is nothing to compare with.
    Ten digits, because with fewer two unrelated numbers meet by chance among the thousands of the
    summaries. So this finds a copied value; it cannot find one retyped with fewer digits."""
    files, factors = tracked(), sorted(glob.glob(os.path.join(ROOT, "data", "factors", "*.json")))
    if files is None or not factors:
        pytest.skip("needs a git checkout and the local factor file")
    values = set()

    def collect(x):
        if isinstance(x, dict):
            for v in x.values():
                collect(v)
        elif isinstance(x, list):
            for v in x:
                collect(v)
        elif isinstance(x, float) and x != 0:
            digits = f"{abs(x):.9e}".split("e")[0].replace(".", "")
            if len(digits.rstrip("0")) >= 9:               # round numbers say nothing
                values.add(digits)
    for path in factors:
        for entry in json.load(open(path, encoding="utf-8"))["factors"].values():
            collect(entry.get("impacts"))
    assert len(values) > 100
    number = re.compile(r"\d+\.\d+(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+")
    found = []
    for f in files:
        if not f.endswith((".py", ".md", ".json", ".csv", ".tex", ".txt", ".toml", ".yml", ".sh", ".ipynb", ".cff")):
            continue
        try:
            text = read(f)
        except UnicodeDecodeError:
            continue
        for m in set(number.findall(text)):
            try:
                x = float(m)
            except ValueError:
                continue
            written = len(re.sub(r"\D", "", re.split("[eE]", m)[0]).strip("0"))
            if x and written >= 9 and f"{abs(x):.9e}".split("e")[0].replace(".", "") in values:
                found.append((f, m))
    assert not found, f"values of the factor file in tracked files: {found[:10]}"
