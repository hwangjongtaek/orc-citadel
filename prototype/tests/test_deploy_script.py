"""deploy.sh 연결 실패 판정 — 계약 TDD (2026-09-25·26 실측 오동작).

호스트가 내려가 있을 때 배포를 돌리면 이렇게 나왔다:

    ssh: connect to host 10.0.0.11 port 22: Operation timed out
    == first-run: 원격 디렉터리 및 .env 프로비저닝 ==
    ssh: connect to host 10.0.0.11 port 22: Operation timed out

**연결 실패를 "한 번도 배포된 적 없는 호스트" 로 판정한다.** 원인은
`ssh "$HOST" "test -d ..." || FIRST=1` 이 명령이 false 를 돌려준 것과 ssh 가 아예
붙지 못한 것을 구분하지 않는다는 것이다. 이번에는 뒤따르는 ssh 도 같이 실패해서
무해했지만, 반쯤 살아 있는 호스트에서는 **`.env` 존재 확인이 실패하는 것만으로
템플릿이 운영 크리덴셜을 덮어쓴다** (`cp .env.production.example .env`).
스크립트가 선언한 계약("절대 .env 을 전송/덮어쓰지 않는다")이 바로 그 경로에서
깨진다.

스크립트는 실행하되 ssh·rsync 는 가짜로 세운다 — 원격 접속 없이 분기만 본다.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy.sh"


def _fake_bin(tmp_path: Path, *, ssh_exit: int) -> Path:
    """PATH 앞에 둘 가짜 ssh/rsync — 호출을 기록하고 정해진 코드로 끝난다."""
    binned = tmp_path / "bin"
    binned.mkdir()
    log = tmp_path / "calls.log"
    (binned / "ssh").write_text(
        "#!/bin/sh\n"
        f'echo "ssh $*" >> "{log}"\n'
        'echo "ssh: connect to host port 22: Operation timed out" >&2\n'
        f"exit {ssh_exit}\n")
    (binned / "rsync").write_text(
        "#!/bin/sh\n"
        f'echo "rsync $*" >> "{log}"\n'
        "exit 0\n")
    for name in ("ssh", "rsync"):
        (binned / name).chmod(0o755)
    return binned


def _run(tmp_path: Path, *, ssh_exit: int) -> tuple[subprocess.CompletedProcess, str]:
    binned = _fake_bin(tmp_path, ssh_exit=ssh_exit)
    env = dict(os.environ, PATH=f"{binned}:{os.environ['PATH']}")
    proc = subprocess.run([str(SCRIPT), "unreachable.test"], env=env,
                          capture_output=True, text=True, timeout=60)
    log = tmp_path / "calls.log"
    return proc, log.read_text() if log.exists() else ""


def test_unreachable_host_is_not_treated_as_a_first_run(tmp_path):
    """ssh 가 255(연결 실패)로 끝나면 프로비저닝 분기로 들어가면 안 된다."""
    proc, _ = _run(tmp_path, ssh_exit=255)

    assert proc.returncode != 0, "연결 실패인데 성공으로 끝났다"
    assert "first-run" not in proc.stdout, proc.stdout
    combined = proc.stdout + proc.stderr
    assert "연결" in combined, f"왜 멈췄는지 말하지 않는다: {combined}"


def test_unreachable_host_stops_before_transferring_anything(tmp_path):
    """접속도 못 하는 호스트에 rsync 를 시도할 이유가 없다."""
    _, calls = _run(tmp_path, ssh_exit=255)

    assert "rsync" not in calls, f"연결 실패 후에도 전송을 시도했다: {calls}"


def test_provisioning_never_overwrites_an_existing_env(tmp_path):
    """계약: 절대 .env 을 전송/덮어쓰지 않는다 — 조건 없는 cp 는 그 계약을 깬다."""
    body = SCRIPT.read_text(encoding="utf-8")

    for line in body.splitlines():
        if "cp .env.production.example" in line:
            assert "-f .env" in line or "cp -n" in line, (
                f"덮어쓰기를 막는 가드가 없다: {line.strip()}")
            break
    else:  # pragma: no cover - 프로비저닝 경로가 사라지면 그때 재검토
        pytest.fail(".env 프로비저닝 경로를 찾지 못했다")
