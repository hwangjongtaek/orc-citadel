"""공용 pytest 설정 — tests/ 디렉터리를 import 경로에 올린다.

tests 는 패키지가 아니어서(`__init__.py` 없음) 테스트 모듈끼리 helper 를
import 할 수 없었다. rootdir prepend 는 수집된 파일 기준이라 모듈 간
의존(test_frontend_dist → test_viewer_static._get)에는 부족하다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
