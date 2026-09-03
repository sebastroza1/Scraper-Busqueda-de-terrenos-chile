from pathlib import Path


def test_python_backend_has_single_canonical_package_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert (repo_root / "python_engine" / "src" / "landfinder").is_dir()
    assert (repo_root / "python_engine" / "pyproject.toml").is_file()
    assert (repo_root / "python_engine" / "src" / "landfinder" / "storage" / "schema.sql").is_file()

    assert not (repo_root / "src" / "landfinder").exists()
    assert not (repo_root / "pyproject.toml").exists()
    assert not (repo_root / "src" / "landfinder" / "storage" / "schema.sql").exists()
