"""Where the data files of BRANCH are. The one place that knows.

The files that BRANCH reads at run time (RUNTIME_DATA) travel with the code in every form it is
delivered: in a clone of the repository they are the folder data/ beside the package; in an
installed package and in the desktop application they are the folder data/ inside the package.
The installer, the package build and the tests take the list from here, so a new folder of data
is added in this file and nowhere else.
"""
import os

RUNTIME_DATA = ("regions", "materials", "benchmark", "cff", "databases")

_PACKAGE = os.path.dirname(os.path.abspath(__file__))


def data_root() -> str:
    """The folder that holds the data. BRANCH_DATA, when set, wins."""
    given = os.environ.get("BRANCH_DATA")
    if given:
        return given
    inside = os.path.join(_PACKAGE, "data")                       # installed package, desktop application
    beside = os.path.join(os.path.dirname(_PACKAGE), "data")      # clone of the repository
    return inside if os.path.isdir(os.path.join(inside, RUNTIME_DATA[0])) else beside


def data_path(*parts: str) -> str:
    """The path of a folder or file of data, for example data_path("regions", "PT.json")."""
    return os.path.join(data_root(), *parts)
