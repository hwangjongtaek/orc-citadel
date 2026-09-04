#!/usr/bin/env bash
# 대상(orchwang-macbookpro)에 이 Mac의 공개키를 ssh-copy-id 로 심는다 (1회용 프로비저닝).
# ssh-copy-id 가 비밀번호를 직접 받으므로 긴 명령을 터미널에 붙여넣지 않아도 된다.
set -euo pipefail
ssh-copy-id -i "${HOME}/.ssh/hwangjongtaek.pub" \
  -o StrictHostKeyChecking=accept-new \
  orchwang@orchwang-macbookpro
echo "== 설치 후 원격 지문 =="
ssh -o BatchMode=yes orchwang@orchwang-macbookpro \
  'wc -l < ~/.ssh/authorized_keys; ssh-keygen -lf ~/.ssh/authorized_keys || cat ~/.ssh/authorized_keys'
