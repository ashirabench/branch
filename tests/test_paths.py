"""One list says which data BRANCH reads at run time; every way of delivering BRANCH takes it from there."""
import os
import re

from branch import paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_every_folder_of_the_list_exists_and_is_found():
    for sub in paths.RUNTIME_DATA:
        assert os.path.isdir(paths.data_path(sub)), sub
    assert os.path.isfile(paths.data_path("regions", "PT.json"))


def test_another_folder_can_be_given(monkeypatch, tmp_path):
    monkeypatch.setenv("BRANCH_DATA", str(tmp_path))
    assert paths.data_path("regions") == os.path.join(str(tmp_path), "regions")


def test_the_installed_package_carries_exactly_these_folders():
    listed = re.search(r'"branch\.data" = \[([^\]]+)\]', read("pyproject.toml")).group(1)
    folders = {m.split("/")[0] for m in re.findall(r'"([^"]+)"', listed)}
    assert folders == set(paths.RUNTIME_DATA)
    # and every file of those folders has a pattern that takes it (a README stays behind)
    patterns = re.findall(r'"([^"]+)"', listed)
    for sub in paths.RUNTIME_DATA:
        for name in os.listdir(paths.data_path(sub)):
            ext = os.path.splitext(name)[1]
            if name == "README.md":
                continue
            assert f"{sub}/*{ext}" in patterns, f"{sub}/{name} would not be in the installed package"


def test_no_module_finds_the_data_on_its_own():
    """Only branch/paths.py computes where the data is."""
    for name in os.listdir(os.path.join(ROOT, "branch")):
        if name.endswith(".py") and name != "paths.py":
            assert "os.path.dirname(os.path.dirname(" not in read("branch", name), name


def test_the_installer_and_the_image_take_the_list_from_here():
    assert "from branch.paths import RUNTIME_DATA" in read("packaging", "branch.spec")
    docker = read("Dockerfile")
    assert "COPY data ./data" in docker and not re.search(r"COPY data/\w+", docker)
