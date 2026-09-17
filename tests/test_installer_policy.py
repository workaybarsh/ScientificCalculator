from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "installer.iss"


def test_uninstall_clears_only_the_fixed_application_data_directory():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert 'Type: filesandordirs; Name: "{localappdata}\\ScientificCalculator"' in installer
    assert "ProfileDirectory := GetEnv('USERPROFILE');" in installer
    assert "GetEnv('HOMEDRIVE') + GetEnv('HOMEPATH')" in installer
    assert "DelTree(FallbackDirectory, True, True, True);" in installer
    assert 'Type: filesandordirs; Name: "{app}"' not in installer
    assert 'Type: dirifempty; Name: "{app}"' in installer


def test_installer_accepts_a_release_selected_x64_or_arm64_architecture_and_filename():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert '#define MyAppArchitecture "x64compatible"' in installer
    assert '#define MyOutputBaseFilename "ScientificCalculator_Setup"' in installer
    assert "OutputBaseFilename={#MyOutputBaseFilename}" in installer
    assert "ArchitecturesAllowed={#MyAppArchitecture}" in installer
    assert "ArchitecturesInstallIn64BitMode={#MyAppArchitecture}" in installer


def test_uninstall_closes_the_running_calculator_before_removing_its_files():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "CurUninstallStep = usUninstall" in installer
    assert "taskkill.exe" in installer
    assert "/F /IM \"{#MyAppExeName}\"" in installer
