"""브랜드 로고 반입 (FR-4, specs/ui-overhaul-astryx TS-4) — 1회성 파생 스크립트.

입력: 가로 lockup 원본 PNG (crest+레터링 통합, near-white 배경이 구워진 판).
처리: 테두리 flood fill 배경 제거 + 밀폐 포켓(글자 counter) 제거 → 투명화
      → 투명 세로 갭 기준 mark/title 분리 → favicon 파생.
pixel art + 소프트 드롭섀도 원본이라, 배경 제거 후 경계의 밝은 픽셀은
'흰 배경 위 검은 그림자' 가정으로 unblend 해 halo 를 줄인다.

사용: python3 scripts/brand_logo_intake.py <lockup-원본.png>
의존: Pillow (시스템 python3 — 저작 도구, 런타임 무관)
산출(2026-09-08 커밋): docs/mockups/assets/{logo-lockup,logo-mark,logo-title,
      favicon-32,apple-touch-180}.png
"""
import sys
import tempfile
from collections import deque
from pathlib import Path

from PIL import Image

SRC = Path(sys.argv[1])
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'mockups' / 'assets'
SCRATCH = Path(tempfile.gettempdir())

NEAR_WHITE = 232  # min(r,g,b) >= 이 값이면 배경 후보


def remove_background(im: Image.Image) -> Image.Image:
    im = im.convert('RGBA')
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        if not (0 <= x < w and 0 <= y < h):
            continue
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        r, g, b, a = px[x, y]
        if min(r, g, b) < NEAR_WHITE:
            continue
        px[x, y] = (0, 0, 0, 0)
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    # 밀폐 포켓 — 테두리에서 못 닿는 글자 counter 안쪽의 near-white 덩어리.
    # 연결 성분이 MIN_POCKET 이상이면 배경으로 판정해 제거한다 (미세 하이라이트 보존).
    MIN_POCKET = 60
    visited = bytearray(w * h)
    for sy in range(h):
        for sx in range(w):
            si = sy * w + sx
            if visited[si] or seen[si]:
                continue
            r, g, b, a = px[sx, sy]
            if a == 0 or min(r, g, b) < NEAR_WHITE:
                visited[si] = 1
                continue
            comp, qq = [], deque([(sx, sy)])
            visited[si] = 1
            while qq:
                x, y = qq.popleft()
                comp.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if not visited[ni]:
                            rr, gg, bb, aa = px[nx, ny]
                            if aa and min(rr, gg, bb) >= NEAR_WHITE:
                                visited[ni] = 1
                                qq.append((nx, ny))
            if len(comp) >= MIN_POCKET:
                for x, y in comp:
                    px[x, y] = (0, 0, 0, 0)
    # unblend: 투명과 맞닿은 밝은 회색(그림자 가장자리)을 반투명 검정으로
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            v = min(r, g, b)
            sat = max(r, g, b) - v
            if v >= 190 and sat <= 14:  # 밝은 무채색 = 그림자 잔가장자리
                near_clear = any(
                    0 <= x + dx < w and 0 <= y + dy < h and px[x + dx, y + dy][3] == 0
                    for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))
                if near_clear:
                    alpha = 255 - v
                    px[x, y] = (0, 0, 0, alpha)
    return im


def alpha_cols(im):
    w, h = im.size
    alpha = im.getchannel('A')
    data = alpha.load()
    return [sum(data[x, y] for y in range(h)) for x in range(w)]


def bbox_crop(im):
    return im.crop(im.getbbox())


im = remove_background(Image.open(SRC))
cols = alpha_cols(im)
w, h = im.size
# 좌측 덩어리(mark)와 우측 덩어리(title) 사이의 최장 무알파 갭 탐색
gaps, run, start = [], 0, None
for x, v in enumerate(cols):
    if v == 0:
        if start is None:
            start = x
        run += 1
    else:
        if start is not None and run > 20:
            gaps.append((run, start, x))
        start, run = None, 0
inner = [g for g in gaps if g[1] > w * 0.15 and g[2] < w * 0.85]
assert inner, f'내부 갭을 찾지 못함: {gaps[:5]}'
_, gs, ge = max(inner)
split = (gs + ge) // 2
print('split at x =', split, 'gap', (gs, ge))

full = bbox_crop(im)
mark = bbox_crop(im.crop((0, 0, split, h)))
title = bbox_crop(im.crop((split, 0, w, h)))
full.save(OUT / 'logo-lockup.png')
mark.save(OUT / 'logo-mark.png')
title.save(OUT / 'logo-title.png')
print('lockup', full.size, '· mark', mark.size, '· title', title.size)

# favicon 파생 — mark 정방형 캔버스 중앙 배치 후 정수비 축소
side = max(mark.size)
sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
sq.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
sq.resize((32, 32), Image.LANCZOS).save(OUT / 'favicon-32.png')
sq.resize((180, 180), Image.LANCZOS).save(OUT / 'apple-touch-180.png')

# 다크 배경 합성 프리뷰 (halo 검수용)
prev = Image.new('RGBA', (full.width + 80, full.height + 80), (17, 24, 32, 255))
prev.alpha_composite(full, (40, 40))
prev.convert('RGB').save(SCRATCH / 'preview-dark.png')
print('preview →', SCRATCH / 'preview-dark.png')
