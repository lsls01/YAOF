#!/usr/bin/env python3
"""Check, verify and publish the R5C build using repository-owned state."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".build"
STATE = ROOT / ".state/r5c.json"
PROTECTED = (".github/", ".state/", "tests/", "scripts/firmware.py",
             "profiles/r5c.json", "files/etc/board.d/99-lsls-network")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fingerprint(inputs):
    return digest(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode())


def request(url):
    headers = {"User-Agent": "YAOF-R5C-build"}
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90)


def fetch(url):
    with request(url) as response:
        return response.read()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def config():
    return json.loads((ROOT / "profiles/r5c.json").read_text())


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def outputs(**values):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


def latest_version(listing, series):
    if not re.fullmatch(r"\d+\.\d+", series):
        raise ValueError("Invalid stable release series")
    versions = set(re.findall(r'href="(\d+\.\d+\.\d+)/"', listing))
    compatible = [v for v in versions if v.startswith(series + ".")]
    if not compatible:
        raise ValueError("No published stable release in the configured series")
    return max(compatible, key=lambda v: tuple(map(int, v.split("."))))


def resolve():
    cfg = config()
    version = latest_version(fetch("https://downloads.openwrt.org/releases/").decode(),
                             cfg["release_series"])
    base = f'https://downloads.openwrt.org/releases/{version}/targets/{cfg["target"]}/{cfg["subtarget"]}'
    profiles = json.loads(fetch(base + "/profiles.json"))
    if profiles["version_number"] != version or cfg["profile"] not in profiles["profiles"]:
        raise ValueError("The selected release does not publish the requested device")
    name = f'openwrt-imagebuilder-{version}-{cfg["target"]}-{cfg["subtarget"]}.Linux-x86_64'
    sums = {line.split()[-1].lstrip("*"): line.split()[0]
            for line in fetch(base + "/sha256sums").decode().splitlines() if line.strip()}
    sha = sums[name + ".tar.zst"]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Invalid ImageBuilder checksum")
    resolved = {"version": version, "ib_name": name, "ib_sha256": sha,
                "ib_url": base + "/" + name + ".tar.zst",
                "device_packages": profiles["profiles"][cfg["profile"]]["device_packages"]}
    write_json(WORK / "resolved.json", resolved)
    outputs(version=version, ib_sha256=sha)
    print(f"Selected stable release: {version}; ImageBuilder SHA256: {sha}")


def guard_upstream(base, upstream):
    ancestor = git("merge-base", base, upstream)
    changed = git("diff", "--name-only", ancestor, upstream).splitlines()
    blocked = [p for p in changed if any(p == item or p.startswith(item) for item in PROTECTED)]
    if blocked:
        raise ValueError("Upstream changes protected files; manual review required: " + ", ".join(blocked))


def merge_upstream(cfg):
    base = git("rev-parse", "HEAD")
    url = f'https://github.com/{cfg["upstream_repository"]}.git'
    git("fetch", "--no-tags", url, cfg["upstream_branch"])
    upstream = git("rev-parse", "FETCH_HEAD")
    guard_upstream(base, upstream)
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("merge", "--no-ff", "--no-edit", upstream)
    return {"base_sha": base, "upstream_sha": upstream, "tree": git("rev-parse", "HEAD^{tree}")}


def imagebuilder_metadata(archive):
    found = {}
    process = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    stream = process.stdout
    if stream is None:
        process.wait()
        raise ValueError("ImageBuilder decompressor did not provide a stream")
    try:
        with tarfile.open(fileobj=stream, mode="r|") as bundle:
            for member in bundle:
                if member.isfile() and (member.name.endswith("/repositories") or
                                         ("/linux-" in member.name and member.name.endswith("/.config"))):
                    if member.size > 2_000_000:
                        raise ValueError("Unexpectedly large ImageBuilder metadata")
                    metadata = bundle.extractfile(member)
                    if metadata is None:
                        raise ValueError("Unable to read ImageBuilder metadata member")
                    with metadata:
                        found[member.name] = metadata.read().decode()
    finally:
        stream.close()
        return_code = process.wait()
    if return_code != 0:
        raise ValueError("Unable to decompress ImageBuilder")
    repositories = next(value for name, value in found.items() if name.endswith("/repositories"))
    kernel_name, kernel_config = next((name, value) for name, value in found.items()
                                     if name.endswith("/.config"))
    version_match = re.search(r"/linux-(\d+\.\d+\.\d+)/", kernel_name)
    if version_match is None:
        raise ValueError("Unrecognized ImageBuilder kernel version")
    kernel_version = version_match.group(1)
    urls = [line.strip() for line in repositories.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    if not urls or any(not u.startswith("https://downloads.openwrt.org/") or
                       not u.endswith("/packages.adb") for u in urls):
        raise ValueError("Unexpected official ImageBuilder repositories")
    return urls, kernel_version, kernel_config


def kernel_options(text):
    return dict(re.findall(r"^(CONFIG_\w+)=(.+)$", text, re.MULTILINE))


def check_kernel(text, required):
    options = kernel_options(text)
    missing = [key for key in required if options.get(key) not in ("y", "m")]
    if missing:
        raise ValueError("Required eBPF kernel options unavailable: " + ", ".join(missing))
    return {key: options.get(key, "n") for key in [*required, "CONFIG_BPF_UNPRIV_DEFAULT_OFF",
            "CONFIG_DEBUG_INFO_BTF", "CONFIG_XDP_SOCKETS", "CONFIG_DEFAULT_TCP_CONG"]}


def requested_packages(cfg):
    packages = set(cfg.get("extra_packages", []))
    for name in ("packages.common", cfg["packages_profile"]):
        for line in (ROOT / "profiles" / name).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("-"):
                packages.discard(line[1:])
            else:
                packages.add(line)
    return packages


def check(force=False):
    cfg = config()
    resolved = json.loads((WORK / "resolved.json").read_text())
    source = merge_upstream(cfg)
    archive = ROOT / ".cache/imagebuilder" / (resolved["ib_name"] + ".tar.zst")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix(".tmp")
        with request(resolved["ib_url"]) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(archive)
    if file_digest(archive) != resolved["ib_sha256"]:
        archive.unlink()
        raise ValueError("ImageBuilder checksum mismatch; refusing cached or downloaded input")
    urls, kernel_version, kernel_config = imagebuilder_metadata(archive)
    capabilities = check_kernel(kernel_config, cfg["required_kernel_options"])
    runs_url = f'https://api.github.com/repos/{cfg["addon_repository"]}/actions/workflows/{cfg["addon_workflow"]}/runs?per_page=1'
    run = json.loads(fetch(runs_url))["workflow_runs"][0]
    if run["status"] != "completed" or run["conclusion"] != "success":
        raise ValueError("The newest addon feed build is not successfully completed; retry later")
    addon_sha = run["head_sha"]
    key = fetch(cfg["feed_key_url"])
    if digest(key) != cfg["feed_key_sha256"]:
        raise ValueError("Addon signing key changed; manual trust review required")
    (WORK / "custom-feed.rsa.pub").write_bytes(key)
    cleanup_url = f'https://raw.githubusercontent.com/{cfg["addon_repository"]}/{addon_sha}/core/tools/clean-overlay.sh'
    cleanup = fetch(cleanup_url)
    (WORK / "clean-overlay.sh").write_bytes(cleanup)
    indexes = [{"url": url, "sha256": digest(fetch(url))} for url in [*urls, cfg["feed_url"]]]
    recipe = digest(git("ls-tree", "-r", "HEAD", "--", "scripts", "profiles", "files", "tests",
                        ".github/workflows/R5C-OpenWrt.yml").encode())
    inputs = {**resolved, "upstream_sha": source["upstream_sha"], "recipe_sha256": recipe,
              "addon_sha": addon_sha, "cleanup_sha256": digest(cleanup), "indexes": indexes,
              "feed_key_sha256": digest(key), "kernel_version": kernel_version,
              "kernel_config_sha256": digest(kernel_config.encode()), "profile": cfg["profile"],
              "lan_address": cfg["lan_address"]}
    identity = fingerprint(inputs)
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    changed = force or previous.get("fingerprint") != identity
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    tag = f'r5c-{resolved["version"]}-{identity[:12]}-{run_id}-{attempt}'
    plan = {"fingerprint": identity, "inputs": inputs, "source": source, "tag": tag,
            "kernel_capabilities": capabilities, "ib_archive": str(archive.relative_to(ROOT))}
    write_json(WORK / "inputs.json", plan)
    write_json(WORK / "yaof-release.json", {"repository": cfg["release_repository"],
               "profile": cfg["profile"], "tag": tag, "fingerprint": identity})
    (WORK / "kernel.config").write_text(kernel_config)
    outputs(changed=str(changed).lower(), tag=tag, version=resolved["version"],
            upstream_sha=source["upstream_sha"], base_sha=source["base_sha"], source_tree=source["tree"])
    print(f"Repository state: {'build required' if changed else 'already current'}; fingerprint: {identity}")
    print(f"Kernel {kernel_version}; native BTF: {capabilities['CONFIG_DEBUG_INFO_BTF']}; AF_XDP: {capabilities['CONFIG_XDP_SOCKETS']}")


def verify_gzip(path):
    decoder = zlib.decompressobj(31)
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            pending = chunk
            while pending and not decoder.eof:
                size += len(decoder.decompress(pending, 1024 * 1024))
                pending = decoder.unconsumed_tail
            if decoder.eof:
                break
    if not decoder.eof or size < 64 * 1024 * 1024:
        raise ValueError(f"Truncated or unexpectedly small disk image: {path.name}")
    return size


def verify():
    cfg = config()
    plan = json.loads((WORK / "inputs.json").read_text())
    if fingerprint(plan["inputs"]) != plan["fingerprint"]:
        raise ValueError("Build input identity changed")
    git("diff", "--exit-code", "HEAD")
    for index in plan["inputs"]["indexes"]:
        if digest(fetch(index["url"])) != index["sha256"]:
            raise ValueError("A package index changed during the build; retry with a fresh input set")
    ib = ROOT / f'build_{cfg["target"]}_{cfg["subtarget"]}_{cfg["profile"]}' / plan["inputs"]["ib_name"]
    manifests = list((ib / "bin/targets" / cfg["target"] / cfg["subtarget"]).glob(f'*{cfg["profile"]}*.manifest'))
    if len(manifests) != 1:
        raise ValueError("Exactly one device package manifest is required")
    manifest = manifests[0].read_text()
    installed = {line.split()[0]: line.split()[-1] for line in manifest.splitlines() if line.strip()}
    required = requested_packages(cfg) | set(cfg["required_packages"]) | set(plan["inputs"]["device_packages"])
    missing = sorted(required - installed.keys())
    if missing:
        raise ValueError("Required packages absent from the image: " + ", ".join(missing))
    if "kmod-tcp-bbr3" in installed:
        raise ValueError("BBR3 is intentionally excluded from the stable Rockchip image")
    if not installed.get("kernel", "").startswith(plan["inputs"]["kernel_version"]):
        raise ValueError("Installed kernel differs from the checked kernel")
    network = Path("etc/board.d/99-lsls-network")
    roots = [p for p in ib.glob("build_dir/target-*/root-*") if (p / network).is_file()]
    if len(roots) != 1 or (roots[0] / network).read_bytes() != (ROOT / "files" / network).read_bytes():
        raise ValueError("The custom first-boot LAN defaults are absent or modified")
    root = roots[0]
    if (root / "etc/yaof-release.json").read_bytes() != (WORK / "yaof-release.json").read_bytes():
        raise ValueError("The repository-owned firmware version descriptor is missing or modified")
    if (root / "usr/bin/yaof-update").read_bytes() != (ROOT / "files/usr/bin/yaof-update").read_bytes():
        raise ValueError("The repository-owned update checker is missing or modified")
    btf = root / "usr/lib/debug/boot/vmlinux"
    if not btf.is_file() or btf.read_bytes()[:2] != b"\x9f\xeb":
        raise ValueError("Detached BTF is absent or invalid")
    if not (btf.parent / ("vmlinux-" + plan["inputs"]["kernel_version"])).is_file():
        raise ValueError("Detached BTF kernel release does not match the firmware")
    for relative in ("etc/init.d/sys-tuning", "etc/hotplug.d/net/01-maximize_nic_rx_tx_buffers"):
        if not (root / relative).is_file():
            raise ValueError("Upstream runtime optimization is missing: " + relative)
    artifact = ROOT / "artifact"
    images = sorted(artifact.glob("*.img.gz"))
    if len(images) != 2 or {"ext4", "squashfs"} != {p.name.split("-")[-2] for p in images}:
        raise ValueError("Both ext4 and squashfs R5C disk images are required")
    fwtool = ib / "staging_dir/host/bin/fwtool"
    result = []
    for image in images:
        metadata_path = WORK / "image-metadata.json"
        subprocess.run([str(fwtool), "-i", str(metadata_path), str(image)], check=True)
        metadata = json.loads(metadata_path.read_text())
        if "friendlyarm,nanopi-r5c" not in metadata.get("supported_devices", []):
            raise ValueError("Firmware metadata does not support NanoPi R5C")
        result.append({"name": image.name, "sha256": file_digest(image), "size": image.stat().st_size,
                       "disk_bytes": verify_gzip(image), "metadata": metadata})
    (artifact / "packages.manifest").write_text(manifest)
    (artifact / "kernel.config").write_bytes((WORK / "kernel.config").read_bytes())
    plan["images"] = result
    plan["verification"] = {"hardware_tested": False, "default_lan_in_rootfs": cfg["lan_address"],
                            "detached_btf_sha256": file_digest(btf), "required_packages_present": True}
    write_json(artifact / "build-info.json", plan)
    (artifact / "release-notes.md").write_text(
        f"Automated NanoPi R5C build using OpenWrt {plan['inputs']['version']} / Linux {plan['inputs']['kernel_version']}.\n\n"
        f"- Default LAN: `{cfg['lan_address']}/24`. Existing network settings are preserved on configuration-preserving upgrades.\n"
        "- Official kernel and device drivers; upstream system-addon tuning and detached vmlinux-btf are retained.\n"
        "- CI checked image metadata, compression integrity, required packages, rootfs LAN defaults and BTF presence.\n"
        "- Hardware boot, throughput and eBPF verifier acceptance are not tested by CI. This is a prerelease.\n"
        f"- YAOF upstream source: https://github.com/{cfg['upstream_repository']}/tree/{plan['source']['upstream_sha']}\n"
        f"- Addon source: https://github.com/{cfg['addon_repository']}/tree/{plan['inputs']['addon_sha']}\n"
        f"- OpenWrt source: https://github.com/openwrt/openwrt/tree/v{plan['inputs']['version']}\n"
        "- The package manifest and build-info.json record the actual build inputs. See docs/r5c.md for source and license notes.\n"
    )
    files = [*images, artifact / "packages.manifest", artifact / "kernel.config",
             artifact / "build-info.json", artifact / "release-notes.md"]
    (artifact / "sha256sums").write_text("".join(f"{file_digest(p)}  {p.name}\n" for p in files))
    print(f"Verified {len(images)} R5C images, {len(installed)} installed packages and detached BTF")


def validate_publication(directory):
    directory = Path(directory)
    plan = json.loads((directory / "build-info.json").read_text())
    if plan["fingerprint"] != fingerprint(plan["inputs"]):
        raise ValueError("Invalid build fingerprint")
    if (not re.fullmatch(r"r5c-[0-9.]+-[0-9a-f]{12}-[0-9]+-[0-9]+", plan["tag"]) or
            not plan["tag"].startswith(f'r5c-{plan["inputs"]["version"]}-{plan["fingerprint"][:12]}-')):
        raise ValueError("Invalid release tag")
    for key in ("base_sha", "upstream_sha", "tree"):
        if not re.fullmatch(r"[0-9a-f]{40}", plan["source"][key]):
            raise ValueError("Invalid source identity")
    entries = []
    for line in (directory / "sha256sums").read_text().splitlines():
        sha, name = line.split()
        path = directory / name
        if Path(name).name != name or path.is_symlink() or not path.is_file() or file_digest(path) != sha:
            raise ValueError("Invalid published asset: " + name)
        entries.append(name)
    expected = {"build-info.json", "packages.manifest", "kernel.config", "release-notes.md",
                *(i["name"] for i in plan["images"])}
    if set(entries) != expected or len(plan["images"]) != 2:
        raise ValueError("Incomplete publication artifacts")
    for image in plan["images"]:
        if image["sha256"] != file_digest(directory / image["name"]):
            raise ValueError("Image receipt checksum mismatch")
    cfg = config()
    git("fetch", "--no-tags", f'https://github.com/{cfg["upstream_repository"]}.git', cfg["upstream_branch"])
    git("merge-base", "--is-ancestor", plan["source"]["upstream_sha"], "FETCH_HEAD")
    guard_upstream(plan["source"]["base_sha"], plan["source"]["upstream_sha"])
    outputs(tag=plan["tag"], base_sha=plan["source"]["base_sha"],
            upstream_sha=plan["source"]["upstream_sha"], source_tree=plan["source"]["tree"])
    print("Publication artifacts and input identity verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("resolve", "check", "verify", "validate-publication"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--directory", default="incoming")
    args = parser.parse_args()
    if args.command == "resolve":
        resolve()
    elif args.command == "check":
        check(args.force)
    elif args.command == "verify":
        verify()
    else:
        validate_publication(args.directory)
