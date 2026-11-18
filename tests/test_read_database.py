"""The parts of the database reader that need neither Java nor a database."""
import importlib.util
import os
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(os.path.dirname(HERE), "experiments", "openlca", "read_database.py")
spec = importlib.util.spec_from_file_location("read_database", PATH)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def _touch(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").close()
    return path


def test_one_version_of_derby_only(tmp_path):
    """openLCA ships two versions of Derby side by side; both on the same path do not start."""
    for name in ("derby-10.14.2.0.jar", "derby-10.17.1.0.jar", "derbyshared-10.17.1.0.jar", "derbytools-10.17.1.0.jar"):
        _touch(tmp_path, name)
    jars = [os.path.basename(j) for j in reader.find_jars(str(tmp_path))]
    assert jars == ["derby-10.17.1.0.jar", "derbyshared-10.17.1.0.jar"]


def test_no_jars_is_said_in_words(tmp_path):
    with pytest.raises(SystemExit) as stop:
        reader.find_jars(str(tmp_path))
    assert "--libs" in str(stop.value)


def test_the_copy_leaves_locks_and_the_original_alone(tmp_path):
    db = tmp_path / "db_original"
    _touch(db, "service.properties")
    _touch(db, "seg0", "c10.dat")
    _touch(db, "db.lck")
    _touch(db, "_olca_", "index")
    before = sorted(os.listdir(db))
    folder = reader.working_copy(str(db), str(tmp_path / "work"))
    assert os.path.exists(os.path.join(folder, "seg0", "c10.dat"))
    assert not os.path.exists(os.path.join(folder, "db.lck"))
    assert not os.path.exists(os.path.join(folder, "_olca_"))
    assert sorted(os.listdir(db)) == before


def test_a_zolca_file_is_read_too(tmp_path):
    packed = tmp_path / "some.zolca"
    with zipfile.ZipFile(packed, "w") as z:
        z.writestr("service.properties", "")
        z.writestr("seg0/c10.dat", "")
    folder = reader.working_copy(str(packed), str(tmp_path / "work"))
    assert os.path.exists(os.path.join(folder, "service.properties"))


def test_what_is_not_a_database_stops(tmp_path):
    with pytest.raises(SystemExit):
        reader.working_copy(str(_touch(tmp_path, "notes.txt")), str(tmp_path / "work"))


def test_numbers_of_the_reader_are_the_ones_of_the_paper():
    """The reader compares with these; the paper states them. One place must not drift from the other."""
    tex = open(os.path.join(os.path.dirname(HERE), "paper", "main.tex"), encoding="utf-8").read()
    for key in ("processes", "exchanges", "with_pedigree", "wrong_sign_waste_outputs"):
        assert f"{reader.PAPER[key]:,}" in tex, key


def test_queries_only_read():
    for sql in reader.SQL.values():
        assert sql.lstrip().lower().startswith("select")
