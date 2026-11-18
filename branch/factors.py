"""The unit impact factors: the file read once from the database, and one number out of it.

The file is written by experiments/openlca/extract_factors.py or by the desktop application and is
kept out of git: the terms of use of the database do not allow redistributing its values.
"""
import glob
import json
import os
import re
from typing import Optional

from .paths import data_path, factors_dir


def load_factors(path: Optional[str] = None, root: Optional[str] = None) -> dict:
    """The file in BRANCH_FACTORS if that is set, else the newest data/factors/*.json, unless a
    path is given. BRANCH_FACTORS lets every command run on another factor file, such as the
    hybrid of the second database test (experiments/data/make_hybrid_factors.py)."""
    if path is None and root is None:
        path = os.environ.get("BRANCH_FACTORS") or None
    if path is None:
        if root:
            roots = [root]
        else:                       # the repository's data/factors, then the user folder of the desktop application
            roots = [data_path("factors"), factors_dir()]
        files = sorted((f for r in roots for f in glob.glob(os.path.join(r, "*.json"))), key=os.path.getmtime)
        if not files:
            raise FileNotFoundError(
                "No extracted factors found. Run experiments/openlca/extract_factors.py with openLCA open first.")
        path = files[-1]
    with open(path) as fh:
        data = json.load(fh)
    data["path"] = path
    year = re.search(r"(20\d\d)", str(data.get("database", ""))) or re.search(r"(20\d\d)", os.path.basename(path))
    if "20XY" in str(data.get("citation", "")):              # files made before the year was filled in
        data["citation"] = data["citation"].replace("20XY", year.group(1) if year else "2026")
    return data


def factor(data: dict, key: str, category: str) -> float:
    """Unit impact factor from an extract_factors.py file."""
    try:
        return float(data["factors"][key]["impacts"][category])
    except KeyError as exc:
        raise KeyError(f"Factor {key!r} / category {category!r} missing in "
                       f"{data.get('path', 'factors')}. Run experiments/openlca/extract_factors.py "
                       f'--update --only "{key}"') from exc
