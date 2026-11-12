"""One-shot recovery of the exact signed ContentHub 1.5.0 program ZIP."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "ASK-022/video-copy-studio-skill"
VERSION = "1.5.0"
TAG = "contenthub-v" + VERSION
ZIP = "ContentHub-App-v1.5.0-x64.zip"
INSTALLER = "ContentHub-Setup-v1.5.0-x64.exe"
PUBLIC_KEY_SHA = "f8edbc1fb4b2f82d3d1cc47c86eb35f4ace7f143bbe845a1c561d1d932afd2c0"


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha_ok(value):
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value)


def stage_ok(value):
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{40}", value)


def prefix(nonce):
    need(isinstance(nonce, str) and re.fullmatch("[a-f0-9]{32}", nonce), "Invalid one-shot nonce")
    return f"releases/contenthub/staging/{VERSION}/{nonce}/"


def branch(nonce):
    prefix(nonce)
    return f"release/contenthub-v{VERSION}-large-zip-{nonce}"


def verify_package(raw, key_raw):
    need(digest(key_raw) == PUBLIC_KEY_SHA and len(raw) <= 256000, "Public key or envelope format differs")
    key, envelope = json.loads(key_raw), json.loads(raw)
    payload = envelope["payload"]
    signature = base64.b64decode(envelope["signature"], validate=True)
    modulus = int.from_bytes(base64.b64decode(key["modulus"], validate=True), "big")
    sig = int.from_bytes(signature, "big")
    need(key["exponent"] == 65537 and modulus.bit_length() == 3072 and len(signature) == 384 and sig < modulus,
         "RSA signature format differs")
    encoded = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(canonical(payload)).digest()
    expected = b"\0\1" + b"\xff" * (384 - len(encoded) - 3) + b"\0" + encoded
    need(hmac.compare_digest(pow(sig, 65537, modulus).to_bytes(384, "big"), expected), "RSA signature rejected")
    need(payload["format"] == "contenthub-desktop-update/v1" and payload["repository"] == REPO
         and payload["version"] == VERSION and payload["resource_contract"] == 1, "Signed product differs")
    package, = payload["packages"]
    need(package["base_version"] == "*" and package["name"] == ZIP and sha_ok(package["sha256"])
         and type(package["bytes"]) is int and 0 < package["bytes"] < 2 * 1024**3, "Signed whole ZIP differs")
    parts = package["parts"]
    need(1 <= len(parts) <= 150, "Unexpected part count")
    for index, part in enumerate(parts, 1):
        need(part["name"] == f"{ZIP}.part{index:03d}" and type(part["bytes"]) is int
             and 0 < part["bytes"] <= 6 * 1024**2 and sha_ok(part["sha256"]), "Signed part differs")
    need(sum(part["bytes"] for part in parts) == package["bytes"], "Signed byte sum differs")
    return package


def validate_plan(plan):
    need(plan["format"] == "contenthub/one-shot-large-zip/v1" and plan["repository"] == REPO
         and plan["tag"] == TAG and plan["branch"] == branch(plan["nonce"]), "Plan scope differs")
    need(type(plan["release_id"]) is int and plan["release_id"] > 0 and stage_ok(plan["stage_commit"])
         and sha_ok(plan["release_body_sha256"]), "Plan draft identity differs")
    raw = base64.b64decode(plan["envelope"], validate=True)
    key_raw = base64.b64decode(plan["public_key"], validate=True)
    package = verify_package(raw, key_raw)
    assets = plan["assets"]
    signed = [package, *package["parts"]]
    need(set(assets) == {ZIP, INSTALLER, "update.json", "contenthub-resources-r1.json"}
         | {part["name"] for part in package["parts"]}, "Unexpected release asset allowlist")
    for name, asset in assets.items():
        need(set(asset) == {"bytes", "sha256"} and type(asset["bytes"]) is int
             and 0 < asset["bytes"] < 2 * 1024**3 and sha_ok(asset["sha256"]), f"Invalid asset pin: {name}")
    need(assets["update.json"] == {"bytes": len(raw), "sha256": digest(raw)}, "Envelope asset pin differs")
    for item in signed:
        need(assets[item["name"]] == {key: item[key] for key in ("bytes", "sha256")}, "Signed asset pin differs")
    if "installer_parts" in plan:
        installer_parts = plan["installer_parts"]
        need(isinstance(installer_parts, list) and 1 <= len(installer_parts) <= 200, "Unexpected installer chunk count")
        for index, part in enumerate(installer_parts, 1):
            need(set(part) == {"name", "bytes", "sha256"} and part["name"] == f"{INSTALLER}.cachepart{index:03d}"
                 and type(part["bytes"]) is int and 0 < part["bytes"] <= 4 * 1024**2
                 and sha_ok(part["sha256"]), "Unexpected installer chunk pin")
        need(sum(part["bytes"] for part in installer_parts) == assets[INSTALLER]["bytes"], "Installer chunk byte sum differs")
    return package


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError("Unexpected redirect")


class GitHub:
    def __init__(self, token):
        need(token and not any(c.isspace() for c in token), "Official Actions token missing")
        self.headers = {"User-Agent": "ContentHub-1.5.0-Zip-Recovery"}
        self.api_headers = self.headers | {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                           "X-GitHub-Api-Version": "2022-11-28"}
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, suffix):
        url = f"https://api.github.com/repos/{REPO}/{suffix}"
        with self.opener.open(urllib.request.Request(url, headers=self.api_headers), timeout=60) as response:
            return json.load(response)

    def public(self, ref, path, limit):
        need(stage_ok(ref) and re.fullmatch(r"releases/contenthub/[A-Za-z0-9./-]+", path)
             and ".." not in path, "Unexpected public artifact path")
        url = f"https://raw.githubusercontent.com/{REPO}/{ref}/{path}"
        for attempt in range(3):
            try:
                with self.opener.open(urllib.request.Request(url, headers=self.headers), timeout=90) as response:
                    raw = response.read(limit + 1)
                need(len(raw) <= limit, "Oversized public artifact")
                return raw
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                if isinstance(error, urllib.error.HTTPError) and error.code not in (408, 429, 500, 502, 503, 504):
                    raise
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)

    def upload(self, release_id, path, size):
        name = path.name
        need(name in {ZIP, INSTALLER}, "Unexpected upload asset name")
        url = f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name={name}"
        media_type = "application/zip" if name == ZIP else "application/octet-stream"
        headers = self.api_headers | {"Content-Type": media_type, "Content-Length": str(size)}
        with path.open("rb") as source:
            request = urllib.request.Request(url, data=source, headers=headers, method="POST")
            with self.opener.open(request, timeout=1200) as response:
                need(response.status == 201, "Unexpected native upload result")
                return json.load(response)


def exact_asset(asset, expected):
    return (asset["state"] == "uploaded" and asset["size"] == expected["bytes"]
            and asset.get("digest") == "sha256:" + expected["sha256"])


def owned_assets(api, plan):
    release_id = plan["release_id"]
    release = api.get(f"releases/{release_id}")
    need(release["id"] == release_id and release["draft"] is True and release["prerelease"] is False
         and release["tag_name"] == TAG and release["target_commitish"] == plan["stage_commit"]
         and digest(release["body"].encode("utf-8")) == plan["release_body_sha256"], "Exact draft changed")
    tag = api.get(f"git/ref/tags/{TAG}")
    need(tag["ref"] == f"refs/tags/{TAG}" and tag["object"]["type"] == "commit"
         and tag["object"]["sha"] == plan["stage_commit"], "Immutable tag changed")
    found = {}
    for page in (1, 2):
        rows = api.get(f"releases/{release_id}/assets?per_page=100&page={page}")
        for asset in rows:
            name = asset["name"]
            need(name not in found and name in plan["assets"], "Unexpected or duplicate attachment")
            need(exact_asset(asset, plan["assets"][name]), f"Non-exact attachment: {name}")
            found[name] = asset
        if len(rows) < 100:
            break
    need(set(found) | {ZIP, INSTALLER} == set(plan["assets"]), "Existing approved attachment set incomplete")
    return found


def reconstruct(api, ref, remote_prefix, name, expected, parts, folder):
    def fetch(part):
        raw = api.public(ref, remote_prefix + part["name"], part["bytes"])
        need(len(raw) == part["bytes"] and digest(raw) == part["sha256"], "Signed part bytes differ: " + part["name"])
        out = folder / part["name"]
        with out.open("xb") as file:
            file.write(raw)
        return out

    out = folder / name
    whole = hashlib.sha256()
    total = 0
    with ThreadPoolExecutor(max_workers=6) as pool, out.open("xb") as output:
        for index, part_path in enumerate(pool.map(fetch, parts), 1):
            with part_path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(block)
                    whole.update(block)
                    total += len(block)
            if index % 20 == 0:
                print(json.dumps({"asset": name, "verified_parts": index}), flush=True)
    need(total == expected["bytes"] and whole.hexdigest() == expected["sha256"], f"Whole reconstructed asset differs: {name}")
    return out


def main():
    env = os.environ
    nonce = env["CONTENTHUB_NONCE"]
    need(env["GITHUB_REPOSITORY"] == REPO and env["GITHUB_EVENT_NAME"] == "push"
         and env["GITHUB_REF_NAME"] == branch(nonce) and env["GITHUB_RUN_ATTEMPT"] == "1",
         "One-shot GitHub workflow scope differs")
    need(digest(Path(__file__).read_bytes()) == env["CONTENTHUB_RUNNER_SHA"], "Pinned runner differs")
    api = GitHub(env["GH_TOKEN"])
    raw = api.public(env["GITHUB_SHA"], prefix(nonce) + "plan.json", 1024 * 1024)
    need(digest(raw) == env["CONTENTHUB_PLAN_SHA"], "Pinned plan differs")
    plan = json.loads(raw)
    need(plan["nonce"] == nonce, "Plan nonce differs")
    package = validate_plan(plan)
    target_sources = [(ZIP, plan["stage_commit"], "releases/contenthub/files/", package["parts"])]
    if "installer_parts" in plan:
        target_sources.append((INSTALLER, env["GITHUB_SHA"], prefix(nonce) + "cache/", plan["installer_parts"]))
    statuses = {}
    for name, ref, remote_prefix, parts in target_sources:
        found = owned_assets(api, plan)
        status = "already-uploaded"
        if name not in found:
            expected = plan["assets"][name]
            with tempfile.TemporaryDirectory(prefix="contenthub-asset-") as directory:
                file = reconstruct(api, ref, remote_prefix, name, expected, parts, Path(directory))
                found = owned_assets(api, plan)
                if name not in found:
                    try:
                        response = api.upload(plan["release_id"], file, expected["bytes"])
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        found = owned_assets(api, plan)
                        need(name in found, "Unconfirmed upload. Inspect native assets before any new attempt.")
                        status = "recovered-by-readback"
                    else:
                        need(response["name"] == name and exact_asset(response, expected), "Native upload checksum differs")
                        status = "uploaded"
        statuses[name] = status
    final = owned_assets(api, plan)
    need(set(statuses) <= set(final), "Final native readback missing")
    proof = {"ok": True, "release_id": plan["release_id"], "stage_commit": plan["stage_commit"],
             "assets": [{"name": name, "status": status, "id": final[name]["id"], **plan["assets"][name]}
                        for name, status in statuses.items()]}
    print(json.dumps(proof), flush=True)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write("ContentHub release asset native readback\n\n```json\n" + json.dumps(proof, indent=2) + "\n```\n")


if __name__ == "__main__":
    main()
