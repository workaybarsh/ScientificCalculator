from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINUX_PACKAGE = ROOT / "packaging" / "linux" / "build_deb.sh"
MACOS_PACKAGE = ROOT / "packaging" / "macos" / "build_pkg.sh"
MACOS_UNINSTALLER = ROOT / "packaging" / "macos" / "uninstall.sh"
SETUP_WIZARD = ROOT / "packaging" / "setup_wizard.py"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
DEB_SCRIPT = LINUX_PACKAGE.read_text(encoding="utf-8")


def test_linux_package_provides_native_installation_and_a_full_app_reset_on_removal():
    package = LINUX_PACKAGE.read_text(encoding="utf-8")

    assert "dpkg-deb --build" in package
    assert 'if [[ $# -ne 4 ]]' in package
    assert 'case "$architecture" in' in package
    assert "Architecture: $architecture" in package
    assert '"$app_directory/icons/scientific-calculator.png"' in package
    assert "pkill -x ScientificCalculator" in package
    assert 'data="$home/.scientific_calculator/ScientificCalculator"' in package
    assert 'rm -rf -- "$data"' in package


def test_macos_package_provides_native_installation_and_a_user_confirmed_full_uninstall():
    package = MACOS_PACKAGE.read_text(encoding="utf-8")
    uninstaller = MACOS_UNINSTALLER.read_text(encoding="utf-8")

    assert "pkgbuild --root" in package
    assert "Scientific Calculator Uninstaller.app" in package
    assert "<key>CFBundleShortVersionString</key><string>$version</string>" in package
    assert "pkill -x ScientificCalculator" in uninstaller
    assert 'data_path="$HOME/.scientific_calculator/ScientificCalculator"' in uninstaller
    assert "/bin/rm -rf -- \"$data_path\"" in uninstaller
    assert "with administrator privileges" in uninstaller


def test_linux_release_publishes_only_the_deb_and_portable_archive():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    linux_build = workflow.split("  linux-build:", maxsplit=1)[1].split(
        "  linux-publish:", maxsplit=1
    )[0]
    linux_publish = workflow.split("  linux-publish:", maxsplit=1)[1].split(
        "  macos-build:", maxsplit=1
    )[0]

    assert 'application_version="$release_version"' in linux_publish
    assert "from scientific_calculator import __version__" not in linux_publish
    # The graphical .run wizard was withdrawn: it did not launch when clicked.
    assert "_Setup_linux" not in linux_build
    assert "Setup Wizard" not in linux_build
    assert "--hidden-import PIL._tkinter_finder" in linux_build
    assert "xvfb-run -a ./dist/ScientificCalculator/ScientificCalculator --gui-smoke-test" in linux_build
    assert "Create Linux application icon" in linux_build
    assert "mkdir -p dist/ScientificCalculator/icons" in linux_build
    assert "Launch Scientific Calculator.desktop" in linux_build
    assert "linux-x86_64-v*" in workflow
    assert "linux-arm64-v*" in workflow
    assert 'name: release-linux-${{ matrix.asset_architecture }}' in linux_publish
    assert '"release/${{ matrix.native }}"' in linux_publish
    assert '(cd dist && sha256sum "${{ matrix.native }}" "ScientificCalculator-linux-${{ matrix.asset_architecture }}.tar.gz")' in linux_build
    # hicolor only resolves real square sizes.
    assert "icons/hicolor/256x256/apps" in DEB_SCRIPT
    assert "hicolor/480x980" not in DEB_SCRIPT
    # A reinstall has to find no leftovers from the previous version.
    assert "rm -rf -- /opt/ScientificCalculator" in DEB_SCRIPT
    assert "DEBIAN/postinst" in DEB_SCRIPT
    assert "bash packaging/linux/build_deb.sh" in linux_build
    assert "ScientificCalculator-linux-x86_64.deb" in linux_build
    assert "ScientificCalculator-linux-arm64.deb" in linux_build


def test_macos_release_ships_the_pkg_installer_without_a_disk_image():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    windows_publish = workflow.split("  windows-publish:", maxsplit=1)[1].split(
        "  linux-build:", maxsplit=1
    )[0]
    macos_build = workflow.split("  macos-build:", maxsplit=1)[1].split(
        "  macos-publish:", maxsplit=1
    )[0]
    macos_publish = workflow.split("  macos-publish:", maxsplit=1)[1]

    assert "$applicationVersion = $releaseVersion" in windows_publish
    # The .dmg wizard was withdrawn; the .pkg installer is the supported path.
    assert ".dmg" not in macos_build
    assert "Create native macOS application icons" in macos_build
    assert "Image.Resampling.LANCZOS" in macos_build
    assert 'format="PNG"' in macos_build
    assert "sips -z" not in macos_build
    assert "hdiutil create" not in macos_build
    assert "--hidden-import PIL._tkinter_finder" in macos_build
    assert "ScientificCalculator --gui-smoke-test" in macos_build
    assert ".dmg" not in macos_publish
    assert "macos-intel-x64-v*" in workflow
    assert "macos-arm64-v*" in workflow
    assert 'name: release-macos-${{ matrix.architecture }}' in macos_publish
    assert '"release/${{ matrix.native }}"' in macos_publish
    assert "bash packaging/macos/build_pkg.sh" in macos_build
    assert "ScientificCalculator_Setup_macos-intel-x64.pkg" in macos_build
    assert "ScientificCalculator_Setup_macos-m-series.pkg" in macos_build


def test_windows_releases_are_split_between_x64_and_arm64():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    windows_build = workflow.split("  windows-build:", maxsplit=1)[1].split(
        "  windows-publish:", maxsplit=1
    )[0]
    windows_publish = workflow.split("  windows-publish:", maxsplit=1)[1].split(
        "  linux-build:", maxsplit=1
    )[0]

    assert "windows-x64-v*" in workflow
    assert "windows-arm64-v*" in workflow
    assert "windows-x64-v" in windows_build
    assert "windows-arm64-v" in windows_build
    assert 'name: release-windows-${{ matrix.architecture }}' in windows_publish
    assert '".\\release\\${{ matrix.installer }}"' in windows_publish


def test_shared_graphical_setup_wizard_keeps_the_windows_reference_flow_on_macos_and_linux():
    wizard = SETUP_WIZARD.read_text(encoding="utf-8")

    for heading in (
        "Welcome to {APP_NAME}",
        "License Agreement",
        "Select Destination Location",
        "Select Additional Tasks",
        "Ready to Install",
        "Installing",
        "Completing the {APP_NAME} Setup Wizard",
    ):
        assert heading in wizard
    assert "_install_macos_with_authorization" in wizard
    assert "Linux installs must stay inside your home folder." in wizard
    assert "Create a desktop shortcut" in wizard
    assert "scientific-calculator.png" in wizard
