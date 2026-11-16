import contextlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts/firmware.py"
spec = importlib.util.spec_from_file_location("firmware", MODULE)
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)


class VersionAndPolicyTests(unittest.TestCase):
    def test_latest_is_numeric_and_excludes_other_series_and_rc(self):
        listing = ''.join(f'href="{v}/"' for v in ["25.12.9", "25.12.10", "26.1.0", "25.12.11-rc1"])
        self.assertEqual(fw.latest_version(listing, "25.12"), "25.12.10")

    def test_unknown_series_and_invalid_series_fail(self):
        for series in ("25.12", "latest;echo unsafe"):
            with self.assertRaises(ValueError):
                fw.latest_version('href="24.10.8/"', series)

    def test_fingerprint_is_order_independent(self):
        self.assertEqual(fw.fingerprint({"a": 1, "b": 2}), fw.fingerprint({"b": 2, "a": 1}))

    def test_fingerprint_tracks_packages_even_without_version_change(self):
        self.assertNotEqual(fw.fingerprint({"version": "25.12.6", "index": "old"}),
                            fw.fingerprint({"version": "25.12.6", "index": "new"}))

    def test_module_bpf_is_allowed_but_missing_bpf_is_rejected(self):
        cfg = fw.check_kernel("CONFIG_BPF=y\nCONFIG_NET_CLS_BPF=m\n", ["CONFIG_BPF", "CONFIG_NET_CLS_BPF"])
        self.assertEqual(cfg["CONFIG_DEBUG_INFO_BTF"], "n")
        with self.assertRaises(ValueError):
            fw.check_kernel("# CONFIG_BPF is not set\n", ["CONFIG_BPF"])

    def test_rockchip_keeps_bbr3_excluded_and_updater_dependencies_present(self):
        packages = fw.requested_packages(fw.config())
        self.assertNotIn("kmod-tcp-bbr3", packages)
        self.assertIn("vmlinux-btf", packages)
        self.assertIn("curl", packages)
        self.assertIn("jsonfilter", packages)
        self.assertEqual(fw.config()["release_repository"], "lsls01/YAOF")

    def test_protected_upstream_changes_require_review(self):
        for path in (".github/workflows/new.yml", "profiles/r5c.json", "scripts/firmware.py"):
            with patch.object(fw, "git", side_effect=["ancestor", path]):
                with self.assertRaises(ValueError):
                    fw.guard_upstream("base", "upstream")

    def test_ordinary_upstream_changes_are_allowed(self):
        with patch.object(fw, "git", side_effect=["ancestor", "scripts/build.sh\nprofiles/packages.common"]):
            fw.guard_upstream("base", "upstream")

    def test_board_defaults_only_set_ip_and_netmask(self):
        script = (fw.ROOT / "files/etc/board.d/99-lsls-network").read_text()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            library = directory / "functions.sh"
            library.write_text('board_config_update() { echo update; }\n'
                               'ucidef_set_interface() { printf "%s\\n" "$*"; }\n'
                               'board_config_flush() { echo flush; }\n')
            executable = directory / "defaults.sh"
            executable.write_text(script.replace(". /lib/functions/uci-defaults.sh", f'. "{library}"'))
            result = subprocess.check_output(["sh", str(executable)], text=True).splitlines()
            self.assertEqual(result, ["update", f"lan ipaddr {fw.config()['lan_address']} netmask 255.255.255.0", "flush"])

    def test_public_release_uploads_every_checksummed_sidecar(self):
        workflow = (fw.ROOT / ".github/workflows/R5C-OpenWrt.yml").read_text()
        upload = workflow.split('gh release create "$TAG"', 1)[1].split('gh release edit "$TAG"', 1)[0]
        upload = upload.split("--notes-file incoming/release-notes.md", 1)[1]
        for name in ("build-info.json", "kernel.config", "packages.manifest", "release-notes.md", "sha256sums"):
            self.assertIn("incoming/" + name, upload)

    def test_imagebuilder_metadata_reads_real_tar_members(self):
        stream = io.BytesIO()
        entries = {"ib/repositories": b"https://downloads.openwrt.org/packages/packages.adb\n",
                   "ib/build_dir/linux-rockchip/linux-6.12.112/.config": b"CONFIG_BPF=y\n"}
        with tarfile.open(fileobj=stream, mode="w") as bundle:
            for name, data in entries.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        process = unittest.mock.Mock(stdout=io.BytesIO(stream.getvalue()))
        process.wait.return_value = 0
        with patch.object(fw.subprocess, "Popen", return_value=process):
            urls, version, config = fw.imagebuilder_metadata(Path("archive"))
        self.assertEqual(version, "6.12.112")
        self.assertIn("CONFIG_BPF=y", config)
        self.assertEqual(len(urls), 1)

    def test_gzip_integrity_accepts_fwtool_trailer_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.img.gz"
            with gzip.open(image, "wb") as output:
                for _ in range(64):
                    output.write(b"\0" * (1024 * 1024))
            data = image.read_bytes()
            image.write_bytes(data + b"FWTOOL METADATA")
            self.assertEqual(fw.verify_gzip(image), 64 * 1024 * 1024)
            image.write_bytes(data[:-8])
            with self.assertRaises(ValueError):
                fw.verify_gzip(image)


class RepositoryStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / ".build"
        self.work.mkdir()
        self.state = self.root / ".state/r5c.json"
        self.cfg = fw.config()
        self.key = b"trusted key"
        self.cfg["feed_key_sha256"] = fw.digest(self.key)
        self.index = b"package index v1"
        self.run_status = "completed"
        self.source = {"base_sha": "a" * 40, "upstream_sha": "b" * 40, "tree": "c" * 40}
        self.recipe = "stable recipe tree"
        self.archive = self.root / ".cache/imagebuilder/ib.tar.zst"
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(b"verified archive")
        fw.write_json(self.work / "resolved.json", {"version": "25.12.6", "ib_name": "ib",
                      "ib_sha256": fw.file_digest(self.archive), "ib_url": "https://example.invalid/ib",
                      "device_packages": ["kmod-r8169"]})
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (("ROOT", self.root), ("WORK", self.work), ("STATE", self.state)):
            self.stack.enter_context(patch.object(fw, name, value))
        self.stack.enter_context(patch.object(fw, "config", return_value=self.cfg))
        self.stack.enter_context(patch.object(fw, "merge_upstream", side_effect=lambda cfg: self.source.copy()))
        self.stack.enter_context(patch.object(fw, "git", side_effect=lambda *args: self.recipe))
        kernel = '\n'.join(key + "=y" for key in self.cfg["required_kernel_options"])
        self.stack.enter_context(patch.object(fw, "imagebuilder_metadata", return_value=(
            ["https://downloads.openwrt.org/test/packages.adb"], "6.12.112", kernel)))
        self.stack.enter_context(patch.object(fw, "fetch", side_effect=self.fetch))
        self.output = self.stack.enter_context(patch.object(fw, "outputs"))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def fetch(self, url):
        if "/runs?" in url:
            return json.dumps({"workflow_runs": [{"status": self.run_status, "conclusion": "success",
                               "head_sha": "d" * 40}]}).encode()
        if url == self.cfg["feed_key_url"]:
            return self.key
        if url.endswith("clean-overlay.sh"):
            return b"pinned cleanup script"
        return self.index

    def record_success(self):
        fw.check()
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_bytes((self.work / "inputs.json").read_bytes())

    def test_first_build_then_own_state_skips_and_force_rebuilds(self):
        self.record_success()
        identity = json.loads(self.state.read_text())["fingerprint"]
        fw.check()
        self.assertEqual(self.output.call_args.kwargs["changed"], "false")
        fw.check(force=True)
        self.assertEqual(self.output.call_args.kwargs["changed"], "true")
        self.assertEqual(json.loads((self.work / "inputs.json").read_text())["fingerprint"], identity)

    def test_feed_change_with_same_openwrt_version_requires_build(self):
        self.record_success()
        self.index = b"package index v2"
        fw.check()
        self.assertEqual(self.output.call_args.kwargs["changed"], "true")

    def test_recipe_and_upstream_changes_require_build(self):
        self.record_success()
        self.recipe = "changed recipe tree"
        fw.check()
        self.assertEqual(self.output.call_args.kwargs["changed"], "true")
        self.record_success()
        self.source["upstream_sha"] = "e" * 40
        fw.check()
        self.assertEqual(self.output.call_args.kwargs["changed"], "true")

    def test_failed_or_running_feed_does_not_advance_successful_state(self):
        self.record_success()
        previous = self.state.read_bytes()
        self.run_status = "in_progress"
        with self.assertRaises(ValueError):
            fw.check()
        self.assertEqual(self.state.read_bytes(), previous)

    def test_unreviewed_key_rotation_is_rejected(self):
        self.record_success()
        previous = self.state.read_bytes()
        self.key = b"unreviewed replacement key"
        with self.assertRaises(ValueError):
            fw.check()
        self.assertEqual(self.state.read_bytes(), previous)

    def test_corrupt_cached_imagebuilder_is_rejected_and_removed(self):
        self.archive.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            fw.check()
        self.assertFalse(self.archive.exists())


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        inputs = {"version": "25.12.6"}
        identity = fw.fingerprint(inputs)
        tag = f"r5c-25.12.6-{identity[:12]}-123-1"
        self.plan = {"inputs": inputs, "fingerprint": identity, "tag": tag,
                     "source": {"base_sha": "a" * 40, "upstream_sha": "b" * 40, "tree": "c" * 40},
                     "images": []}
        for filesystem in ("ext4", "squashfs"):
            name = f"{tag}-{filesystem}-sysupgrade.img.gz"
            (self.directory / name).write_bytes(b"test firmware")
            self.plan["images"].append({"name": name, "sha256": fw.file_digest(self.directory / name)})
        for name in ("packages.manifest", "kernel.config", "release-notes.md"):
            (self.directory / name).write_text("test metadata\n")
        self.save()

    def save(self):
        fw.write_json(self.directory / "build-info.json", self.plan)
        files = sorted(p for p in self.directory.iterdir() if p.name != "sha256sums")
        (self.directory / "sha256sums").write_text(''.join(f"{fw.file_digest(p)}  {p.name}\n" for p in files))

    def test_verified_assets_are_accepted(self):
        with patch.object(fw, "git", return_value=""), patch.object(fw, "guard_upstream"), patch.object(fw, "outputs"):
            fw.validate_publication(self.directory)

    def test_modified_asset_is_rejected(self):
        (self.directory / "kernel.config").write_text("modified")
        with self.assertRaises(ValueError):
            fw.validate_publication(self.directory)

    def test_incomplete_assets_are_rejected(self):
        sums = self.directory / "sha256sums"
        sums.write_text('\n'.join(sums.read_text().splitlines()[1:]) + '\n')
        with self.assertRaises(ValueError):
            fw.validate_publication(self.directory)

    def test_release_tag_cannot_contain_shell_input(self):
        self.plan["tag"] = "r5c-25.12.6;echo unsafe"
        self.save()
        with self.assertRaises(ValueError):
            fw.validate_publication(self.directory)

    def test_receipt_must_match_actual_image_checksum(self):
        self.plan["images"][0]["sha256"] = "f" * 64
        self.save()
        with self.assertRaises(ValueError):
            fw.validate_publication(self.directory)


if __name__ == "__main__":
    unittest.main()
