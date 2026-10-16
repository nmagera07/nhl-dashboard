import ast
import zipfile
from pathlib import Path

from scripts import package_notifier

BACKEND = Path(package_notifier.__file__).resolve().parent.parent


def local_imports(source):
    """Top-level imports in source that are backend modules (backend/<name>.py)."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return {name for name in names if (BACKEND / f"{name}.py").exists()}


def test_package_has_the_function_and_every_backend_module_it_imports(tmp_path):
    with zipfile.ZipFile(package_notifier.build(tmp_path / "notifier.zip")) as z:
        files = set(z.namelist())
        sources = {name: z.read(name).decode() for name in files if name.endswith(".py")}

    assert {"function_app.py", "host.json", "requirements.txt"} <= files
    for name, source in sources.items():
        missing = {f"{module}.py" for module in local_imports(source)} - files
        assert not missing, f"{name} imports {missing}, which the package leaves out"


def pins(path):
    lines = (line.split("#")[0].strip() for line in path.read_text().splitlines())
    return dict(line.split("==") for line in lines if "==" in line)


def test_function_requirements_match_the_backend_pins():
    backend, function = pins(BACKEND / "requirements.txt"), pins(BACKEND / "notifier_function" / "requirements.txt")
    for package, version in function.items():
        if package in backend:
            assert backend[package] == version, f"{package}: function pins {version}, backend pins {backend[package]}"
