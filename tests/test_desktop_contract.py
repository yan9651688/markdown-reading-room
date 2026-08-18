from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "src-tauri"


class DesktopContractTests(unittest.TestCase):
    def test_versions_and_static_frontend_are_aligned(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
        cargo = (TAURI / "Cargo.toml").read_text(encoding="utf-8")
        rust = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")

        self.assertEqual(package["version"], "0.1.1")
        self.assertEqual(config["version"], package["version"])
        self.assertEqual(config["mainBinaryName"], "Moyue")
        self.assertRegex(cargo, r'(?m)^version = "0\.1\.1"$')
        self.assertIn('const APP_VERSION: &str = "0.1.1";', rust)
        self.assertEqual(config["build"]["frontendDist"], "../assets/app/static")
        self.assertTrue(config["app"]["withGlobalTauri"])

    def test_windows_bundle_and_local_asset_boundaries_are_explicit(self) -> None:
        config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
        capability = json.loads((TAURI / "capabilities" / "default.json").read_text(encoding="utf-8"))

        self.assertEqual(config["bundle"]["targets"], ["nsis"])
        self.assertTrue(config["bundle"]["useLocalToolsDir"])
        self.assertEqual(config["bundle"]["windows"]["webviewInstallMode"]["type"], "embedBootstrapper")
        self.assertTrue(config["app"]["security"]["assetProtocol"]["enable"])
        self.assertEqual(config["app"]["security"]["assetProtocol"]["scope"], [])
        self.assertEqual(capability["windows"], ["main"])
        self.assertEqual(capability["permissions"], ["core:default"])

    def test_runtime_commands_match_registered_tauri_commands(self) -> None:
        runtime = (ROOT / "assets" / "app" / "static" / "runtime.js").read_text(encoding="utf-8")
        rust = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
        registered_block = re.search(r"generate_handler!\s*\[([^]]+)]", rust, re.DOTALL)
        self.assertIsNotNone(registered_block)

        commands = {
            "health",
            "get_config",
            "get_tree",
            "search_documents",
            "read_document",
            "resolve_asset_path",
            "discover_libraries",
            "pick_discovery_root",
            "pick_libraries",
            "add_discovered_libraries",
            "remove_library",
        }
        for command in commands:
            self.assertIn(command, registered_block.group(1))
            self.assertIn(f'"{command}"', runtime)

    def test_windows_release_script_is_wired_to_the_desktop_build(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        script = (ROOT / "scripts" / "build_windows_release.ps1").read_text(encoding="ascii")

        self.assertEqual(package["scripts"]["desktop:build"], "tauri build --bundles nsis")
        self.assertIn("Launch-VsDevShell.ps1", script)
        self.assertIn("MoyueBuildTemp", script)
        self.assertIn("LOCALAPPDATA", script)
        self.assertIn("npm_config_cache", script)
        self.assertIn('$desktopExecutable = Join-Path $targetRoot "Moyue.exe"', script)
        self.assertIn('$setupPath = Join-Path $outputPath "Moyue-Setup.exe"', script)
        self.assertIn('$portablePath = Join-Path $outputPath "Moyue.exe"', script)
        self.assertIn("release-manifest.json", script)


if __name__ == "__main__":
    unittest.main()
