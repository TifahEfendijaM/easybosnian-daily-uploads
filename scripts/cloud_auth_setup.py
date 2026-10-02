"""Dedicated browser login; never copies the desktop Codex session or prints credentials."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

from easybosnian.cloud_prepare import managed_auth
from easybosnian.core import ROOT, REPO, gh, verify_repository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["login", "save"])
    parser.add_argument("--device-auth", action="store_true", help="Complete dedicated sign-in from another device, such as a phone")
    args = parser.parse_args()
    action = args.action
    verify_repository(remote=True)
    directory = ROOT / "build/cloud-codex-auth"
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    auth = directory / "auth.json"
    if action == "login":
        if auth.exists():
            raise ValueError("Dedicated cloud sign-in already exists; save it without using it on the Mac")
        executable = shutil.which("codex")
        if not executable:
            raise ValueError("Official Codex CLI is unavailable")
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(directory)
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
            environment.pop(key, None)
        log = ROOT / "build/cloud-codex-login.secret"
        with log.open("w") as output:
            log.chmod(0o600)
            command=[executable, "-c", 'cli_auth_credentials_store="file"', "login"]
            if args.device_auth:
                command.append("--device-auth")
            process = subprocess.Popen(command,
                                       env=environment, stdout=output, stderr=subprocess.STDOUT)
        (ROOT / "build/cloud-codex-login.pid").write_text(str(process.pid))
        print("Complete the separate ChatGPT sign-in using the device link/code" if args.device_auth else "Complete the separate ChatGPT sign-in in the browser opened by Codex. No token needs copying.", flush=True)
        try:
            result=process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            process.terminate()
            raise ValueError("Browser sign-in expired; open a fresh dedicated login") from None
        if result or not auth.exists():
            raise ValueError("Browser sign-in did not complete; open a fresh dedicated login")
        print("Separate cloud sign-in completed; ready to save privately", flush=True)
    else:
        if not auth.exists():
            raise ValueError("Separate browser sign-in is not complete yet")
        value = auth.read_text()
        managed_auth(value)
        auth.chmod(0o600)
        gh("secret", "set", "CODEX_AUTH_JSON", "--repo", REPO, input_text=value)
        print("Dedicated cloud ChatGPT sign-in stored privately in the exact repository. Do not run it locally.")


if __name__ == "__main__":
    main()
