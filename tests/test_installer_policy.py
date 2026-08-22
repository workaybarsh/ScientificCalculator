from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "installer.iss"


def test_uninstall_clears_only_the_fixed_application_data_directory():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert 'Type: filesandordirs; Name: "{localappdata}\\ScientificCalculator"' in installer
    assert 'Type: filesandordirs; Name: "{app}"' not in installer
    assert 'Type: dirifempty; Name: "{app}"' in installer
