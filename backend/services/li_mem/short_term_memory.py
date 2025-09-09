# backend/services/li_mem/short_term_memory.py
# 역할: Redis를 사용하여 세션별 STM(단기기억)을 관리하는 모듈
# - 세션별 채팅 기록(chat_history)과 회상된 장기기억 버퍼(recalled_ltm_buffer)를 저장/조회/삭제
# - 터미널 커맨드 : redis-cli FLUSHALL로 전체 STM 초기화 가능

# import 모듈
import redis
from redis import Redis
import json
from datetime import datetime, timezone
import os

# 환경변수 LIRA_DEBUG=1일 경우, 디버그 로그 출력 활성화
# .env 파일에서 디버깅모드 설정을 한다. 
# 디버깅 모드일 경우에는 STM등 처리내역이 확인되나, 확인시 보안 문제가 될 수 있으므로 주의
DEBUG = os.getenv("LIRA_DEBUG", "0") == "1"

# Redis 클라이언트 설정 (localhost에서 실행, DB 0번 사용)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
# redis.from_url()을 사용하여 Redis 클라이언트를 생성
# redis: -> Redis 서버에 연결한다는 뜻(Redis 라이브러리에서만 지원하는 연결문자열 방식, 파이썬 미지원)
redis_client: Redis = redis.from_url(REDIS_URL, decode_responses=True)

# 세션 만료 시간 (초 단위) -> 24시간 후 redis(STM) 자동 삭제
SESSION_EXPIRATION_SECONDS = 24 * 60 * 60

# Redis에서 특정 세션의 STM 데이터를 가져온다.
# STM의 내용이 존재하지 않으면 기본 구조(빈 채팅 기록, 빈 회상 버퍼, 현재 시간)를 반환.
def get_session_memory(session_id: str) -> dict:

    # session_id를 redis_client.get의 인자로 받기위해 f-string으로 포맷팅 한다.
    session_key = f"session:{session_id}"
    # 고유 세션 id별로 raw_data를 갖는다. -> DB가 테이블을 갖고 있는 것 처럼
    # raw_data : STM에 저장되어 있는 데이터 형태(JSON 문자열)
    raw_data = redis_client.get(session_key)

    # raw_data가 존재하면 JSON으로 파싱하여 STM 데이터를 반환
    if raw_data:
        return json.loads(raw_data)
    else:
        # STM 데이터가 없으면 기본 구조(빈 채팅 기록, 빈 회상 버퍼, 현재 시간)를 반환
        return {
            "chat_history": [],
            "recalled_ltm_buffer": [],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

# 세션 STM 데이터를 갱신한다.
# Redis는 세션별 단기 보관(TTL) 용도로 사용하며,
# 매번 전체 stm_data(JSON)를 직렬화하여 동일 key에 덮어쓴다(append -> update).
# -> key: session:{session_id}
# -> value: {"chat_history":[...], "recalled_ltm_buffer":[...], "last_updated":"..."}
def update_session_memory(session_id: str, stm_data: dict) -> bool:
    # session_id를 redis_client.set의 인자로 받기위해 f-string으로 포맷팅 한다.
    session_key = f"session:{session_id}"
    # STM 데이터가 업데이트(수정)된 시간 갱신
    stm_data["last_updated"] = datetime.now(timezone.utc).isoformat()
    # Redis에서 업데이트 내용을 저장처리
    redis_client.set(
        session_key,
        json.dumps(stm_data),
        # json.dumps : 딕셔너리를 JSON 문자열로 변환되는 예시
        # 예시) json.dumps로 변환 전/후
        # 1. STM에 저장 전 데이터 (파이썬 딕셔너리)
        # {
        #   "chat_history": [
        #     {"role": "user", "content": "안녕 리라야!"},
        #     {"role": "lira", "content": "안녕하세요! 잘 지내셨나요?"}
        #   ],
        #   "recalled_ltm_buffer": [
        #     {
        #       "source": "LTM_Recall",
        #       "text": "기억해줘. 내가 좋아하는 커피는 아메리카노야.",
        #       "timestamp": "2025-08-11T13:45:22.123456+00:00"
        #     }
        #   ],
        #   "last_updated": "2025-08-11T13:45:22.123456+00:00"
        # }

        #  2. STM에 저장 후 데이터 (Redis에 저장된 문자열)
        #  -> json.dumps(stm_data)로 stm_data를 받아서 직렬화하여 Redis에 문자열로 저장한 결과(raw_data)가 아래.
        #
        # '{
        #   "chat_history": [
        #     {"role": "user", "content": "안녕 리라야!"},
        #     {"role": "lira", "content": "안녕하세요! 잘 지내셨나요?"}
        #   ],
        #   "recalled_ltm_buffer": [
        #     {
        #       "source": "LTM_Recall",
        #       "text": "기억해줘. 내가 좋아하는 커피는 아메리카노야.",
        #       "timestamp": "2025-08-11T13:45:22.123456+00:00"
        #     }
        #   ],
        #   "last_updated": "2025-08-11T13:45:22.123456+00:00"
        # }'

        #  redis.client.set함수에 ex인자로 들어가는게 TTL시간
        ex=SESSION_EXPIRATION_SECONDS
    )

    if DEBUG:
        # 디버그 모드일 때, 업데이트된 STM 데이터를 출력
        print(f"[STM] Session {session_id} updated.")
    return True

# 채팅 내용을 STM의 chat_history에 추가한다.
# - session_id: 세션 식별자
# - role: "user" 또는 "lira" 중 하나.
# - content: 채팅 내용
def append_chat_history(session_id: str, role: str, content: str):
    # 기존의 세션 아이디를 통해 redis에서 STM 데이터를 가져온다.
    stm_data = get_session_memory(session_id)
    # stm_data의 딕셔너리에 새로운 채팅기록을 추가
    stm_data["chat_history"].append({"role": role, "content": content})
    # STM 데이터를 update함수를 사용하여, Redis에 저장
    update_session_memory(session_id, stm_data)

# LTM에서 회상된 문장을 STM의 recalled_ltm_buffer에 추가한다.
# - session_id: 세션 식별자
# - source: 회상의 출처(예: "LTM_Recall")
# - text: 회상된 문장 내용
# - timestamp: datetime 또는 문자열(ISO 추천). 값이 없으면 현재 UTC 시각으로 자동 기록.
def append_ltm_recall(session_id: str, source: str, text: str, timestamp=None):
    # 1) timestamp 정규화
    iso_ts = None
    if isinstance(timestamp, datetime):
        iso_ts = timestamp.astimezone(timezone.utc).isoformat()
    elif isinstance(timestamp, str) and timestamp.strip():
        iso_ts = timestamp.strip()
    else:
        iso_ts = datetime.now(timezone.utc).isoformat()

    # 2) 기존의 세션 아이디를 통해 redis에서 STM 데이터를 가져온다.
    stm_data = get_session_memory(session_id)

    # 3) stm_data의 딕셔너리 recalled_ltm_buffer에 새로운 회상된 문장을 추가(+ 타임스탬프)
    stm_data["recalled_ltm_buffer"].append({
        "source": source,
        "text": text,
        "timestamp": iso_ts
    })

    # 4) STM 데이터를 update함수를 사용하여, Redis에 저장
    update_session_memory(session_id, stm_data)

# 특정 세션의 STM 데이터를 삭제한다.
def clear_session_memory(session_id: str):
    # session_id를 redis_client.delete의 인자로 받기위해 f-string으로 포맷팅 한다.
    session_key = f"session:{session_id}"
    # Redis에서 해당 세션 키를 삭제
    redis_client.delete(session_key)
    if DEBUG:
        print(f"[STM] Session {session_id} cleared.")