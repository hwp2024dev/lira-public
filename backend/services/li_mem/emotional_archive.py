# emotional_archive.py
# role: 사용자 입력 내용 중 기억 저장소 (LTM: user_id 기준)
# content: mongoDB에서 기억을 저장하고 불러오는 기능을 담당.

# import
import re
import os
from pymongo import MongoClient
from datetime import datetime, timezone
from backend.utils.keyword_extractor import extract_keywords

# 디버그 플래그 추가 (파일 내에서 사용하기 위함)
DEBUG = os.getenv("LIRA_DEBUG", "0") == "1"

# ===== MongoDB 설정 =====
# 환경변수 기반 설정 (없으면 기본값 사용)
# - MONGO_URL:      mongodb 접속 URL
# - MONGO_DB_NAME:  사용할 DB 이름 (기본: lira_memory)
# - MONGO_COLLECTION: 사용할 컬렉션 이름 (기본: memory)
client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017/"))
db = client[os.getenv("MONGO_DB_NAME", "lira_memory")]
collection = db[os.getenv("MONGO_COLLECTION", "memory")]

# 사용자 단위 최신 데이터 조회를 빠르게 하기 위한 인덱스(검색조건) 생성 / 여기서의 인덱스는 색인, 목차가 아닌 검색을 빠르게 하기위한 정보카드라 생각하면 좋음
def _ensure_indexes():
    try:
        # MongoDB 컬렉션에 검색조건을 생성한다.
        # 검색 대상: user_id(오름차순=1), timestamp(내림차순=-1) -> 동일 사용자 기준 최신 데이터 조회 최적화
        collection.create_index([("user_id", 1), ("timestamp", -1)])
    except Exception as e:
        # 검색조건 생성이 실패했을 경우 (예: 이미 존재하거나 DB 문제 발생)
        if DEBUG:
            # 디버그 모드일 때만 오류 메시지를 출력한다.
            print(f"[Mongo] 검색조건 생성에 실패 했습니다 : {e}")

# 모듈이 불러와질 때 자동으로 _ensure_indexes() 함수를 실행해서 인덱스를 보장한다.
# -> 자주 쓰는 쿼리에 대한 인덱스를 미리 생성해두어 성능을 최적화한다.
_ensure_indexes()

# 검색에서 제외할 AI 자신을 지칭하는 키워드 목록
# -> "리라야 내 이름 기억나?" 에서 '리라'는 검색어로 불필요하므로 제외
_SELF_REFERENCE_KEYWORDS = {"리라", "리라야", "어시스턴트", "챗봇", "assistant", "hey lira", "lira"}
# 소문자 집합을 미리 만들어 대소문자 혼용 입력에도 안정적으로 매칭
_SELF_REFERENCE_KEYWORDS_LOWER = {s.lower() for s in _SELF_REFERENCE_KEYWORDS}

# 정렬 시 timestamp 타입 혼합(문자열/Datetime) 안전 변환 키
def _ts_key(v):
    if isinstance(v, datetime):
        return v
    try:
        # ISO 문자열(예: "...Z")도 처리
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return datetime.min

# 감정기반 저장
def store_memory(user_id: str, text: str, emotions: list[dict]) -> bool:
    # 주의: LTM은 사용자 단위로만 저장. session_id는 STM 분리를 위해서만 사용하며 여기서는 저장하지 않는다.
    # 1) 감정 리스트를 표준화된 형태로 변환하기 위한 빈 리스트 생성
    emotion_list = []
    # 2) 감정 분석 결과(emotions)는 [{"label": "...", "score": ...}, ...] 형식
    #    각 감정을 label/score만 뽑아내어 새 리스트에 저장
    for emotion in emotions:
        emotion_list.append({
            "label": emotion["label"],   # 감정 이름 (예: joy, sadness)
            "score": emotion["score"]    # 감정 강도 (0~1 사이)
        })

    # 3) 최종적으로 MongoDB에 넣을 하나의 '기억 문서'를 구성
    memory = {
        "user_id": user_id,             # 사용자 ID (세션 격리를 위해 사용)
        "text": text,                   # 사용자 입력 원문
        "emotions": emotion_list,       # 감정 분석 결과 리스트
        "timestamp": datetime.now(timezone.utc)  # 저장 시각 (UTC 기준)
    }
    
    # 4) MongoDB 컬렉션에 문서를 삽입 (하나의 대화를 문서로 저장)
    collection.insert_one(memory)

    # memory 예시= 
    # {
    #     "_id": ObjectId("66c1d2e4f5a1c3d4e56789ab"),   // MongoDB가 자동으로 생성하는 고유 ID
    #     "user_id": "user_12345",                       // 사용자 식별자
    #     "text": "오늘 하루가 너무 힘들었어...",        // 사용자 입력 텍스트
    #     "emotions": [                                  // 감정 분석 결과 (label, score)
    #         {
    #         "label": "sadness",
    #         "score": 0.812
    #         },
    #         {
    #         "label": "fear",
    #         "score": 0.421
    #         }
    #     ],
    #     "timestamp": ISODate("2025-08-17T12:45:32Z")   // 저장 시점 (UTC)
    # }

    # 5) 성공적으로 삽입되면 True 반환
    return True

# find_memories: 사용자 입력에서 키워드를 뽑아 MongoDB 기억 저장소에서 관련 텍스트를 찾아 반환한다. (user_id 기준 검색)
def find_memories(memory_text: str, user_id: str, find_limit: int = 3):
    # 입력 문장에서 키워드 추출 (최대 3개 반환, 리스트 형태)
    initial_keywords = extract_keywords(memory_text, top_n=3)
    
    # extract_keywords가 문자열 하나만 돌려준 경우(문자열 하나 --> 단일 키워드)
    if isinstance(initial_keywords, str):
        # 값이 비어있지 않으면 [단일 키워드]로 감싸 리스트로 통일, 비어있으면 빈 리스트로
        initial_keywords = [initial_keywords] if initial_keywords else []

    # 그 밖에 리스트/튜플이 아니라면(예: None, dict 등) 전부 무시하고 빈 리스트로 정규화
    elif not isinstance(initial_keywords, (list, tuple)):
        initial_keywords = []

    # 키워드 정규화 + 전처리
    initial_keywords = [
        kw.strip()                                     # 키워드 양쪽 공백 제거 -> 앞뒤 공백 제거
        for kw in initial_keywords                     # initial_keywords 리스트를 순회하면서 -> 문자열만 허용
        if isinstance(kw, str) and kw                  # 문자열이고, None/빈값("")이 아니고 -> 빈 문자열 제외
        and len(kw.strip()) >= 2                       # strip한 뒤 길이가 2글자 이상일 때만 남김 -> 2글자 미만 키워드는 제거
    ]

    # 최종 키워드 리스트 생성: 자기참조 키워드/중복 제거
    # 이미 추가된 키워드 기록
    seen_kw = set()     
    keywords = []
    for kw in initial_keywords:
        # "리라", "assistant" 등 자기 자신은 제외
        if kw.lower() in _SELF_REFERENCE_KEYWORDS_LOWER:   
            continue
        # 1글자 이하 제거
        if len(kw) < 2:                      
            continue
        # 중복 키워드 제거
        if kw in seen_kw:                    
            continue
        # 현재 키워드를 중복 체크용 집합(seen_kw)에 추가    
        seen_kw.add(kw)
        # 최종 검색용 키워드 리스트에 추가       
        keywords.append(kw)   

    # 최종 키워드가 없으면 빈 리스트 반환
    if not keywords:
        return []

    # 디버깅 로그: 최초 추출 키워드 vs 최종 키워드
    if DEBUG:
        print(f"[find_memories] 최초 추출 키워드: {initial_keywords} -> 검색용 최종 키워드: {keywords}")

    all_found_memories = []   # 최종적으로 모을 검색 결과 저장 리스트 초기화

    # 필터링된 키워드 리스트로 반복 검색 실행
    for keyword in keywords:  
        # 키워드가 문자열이 아니거나, 2글자 미만이면 건너뜀
        if not isinstance(keyword, str) or len(keyword) < 2:
            continue

        # MongoDB 정규식(RAW 패턴) 혼동방지 안전 처리 (특수문자 이스케이프)
        # 예 : C++.을 검색했을경우...
        # ---
        # [RAW 패턴 검색 결과] -> 여러가지가 검색 될 수 있다.
        # 매칭: C++.
        # 매칭: C++a
        # 매칭: C++b

        # [ESCAPE 패턴 검색 결과] -> 원본 그대로 검색 된다.
        # 매칭: C++.
        safe_kw = re.escape(keyword)

        # 1차 기본 키워드 검색:
        # - 같은 user_id 범위 안에서
        # - text 필드에 safe_kw가 들어있는 문서 검색
        # - $options: "iu" -> “사용자가 어떤 대소문자로 쓰든, 어떤 언어(한글/영문/특수 유니코드)로 쓰든 안전하게 검색해라” 
        # -> i옵션 : Coffee - coffee로 매칭이 잡힌다. / 대소문자 대응 옵션
        # -> u옵션 : 한국어,일본어 등등 비ASCII 를 커버하기 위해 / 유니코드를 사용하게 해주는 옵션
        base = list(
            collection.find(
                {"user_id": user_id, "text": {"$regex": safe_kw, "$options": "iu"}},
                {"_id": 0}   # MongoDB 기본 제공 필드 "_id"는 제외
            )
            .sort("timestamp", -1)    # 최신순으로 정렬
            .limit(find_limit)        # 검색 결과 개수 제한
        )

        # 검색된 결과를 전체 리스트에 합침
        all_found_memories.extend(base)

# 4) 검색 결과 중복 제거
    # 입력 텍스트를 소문자화, 특수문자 제거
    normalized_input = re.sub(r"\W+", "", memory_text.lower())
    # 이미 처리한 텍스트 집합  
    seen_texts = set()
    # 중복 제거된 결과 저장 리스트    
    filtered = []

    # 모든 검색 결과 순회
    for mem in all_found_memories:
        # memory의 원본 텍스트           
        t = mem.get("text", "")
        # 소문자화 + 특수문자 제거하여 비교용 문자열 생성
        norm_t = re.sub(r"\W+", "", t.lower())

        # 사용자가 방금 입력한 문장과 동일하면 제외
        if norm_t == normalized_input:       
            continue
        # 아직 처리되지 않은 새로운 텍스트라면    
        if norm_t not in seen_texts:
            # 중복 방지를 위해 기록         
            seen_texts.add(norm_t)
            # 결과 리스트에 추가
            filtered.append(mem)

    # 점수와 timestamp 기준으로 정렬 (가장 관련도 높은것, 최신순)
    filtered.sort(key=lambda r: (_score_row(r.get("text", "")), _ts_key(r.get("timestamp", ""))), reverse=True)

    # 최종 결과 제한 개수만 반환
    return filtered[:find_limit]

# 사용자 입력 텍스트가 MongoDB 기억 저장소에 실제로 존재하는지 확인 (user_id 기준 검색)
def confirm_in_mongo(memory_text: str, user_id: str, max_results: int = 1) -> list[dict]:
    # extract_keywords 결과 타입을 정규화하고 첫 번째 유효 토큰을 고른다
    # 첫 번째 유효 토큰 예시:
    # memory_text = "내 이름은 박현우야"
    # extract_keywords(memory_text, top_n=1) 
    # -> ["이름", "박현우"] -> 첫번째 유효토큰: 이름
    raw = extract_keywords(memory_text, top_n=1)
    
    if isinstance(raw, str):
        # 문자열 하나만 온 경우 -> 비어있지 않으면 리스트로 감싼다
        candidates = [raw] if raw else []

    elif isinstance(raw, (list, tuple)):
        # 리스트/튜플인 경우 -> 문자열 요소만 추린다
        candidates = []
        for kw in raw:
            if isinstance(kw, str):
                candidates.append(kw)
    else:
        # 그 외 타입(None 등)은 빈 리스트 처리
        candidates = []

    # 전처리: 공백 제거 후 2글자 미만은 버린다
    processed_candidates = []
    for kw in candidates:
        if kw and len(kw.strip()) >= 2:
            processed_candidates.append(kw.strip())
    candidates = processed_candidates
    # 검색에 사용할 최종 키워드 하나 선택(없으면 빈 문자열)
    keyword = candidates[0] if candidates else ""

    # 키워드가 비어있으면 즉시 빈 결과 반환
    if not keyword:
        return []

    # 정규식 안전 처리(특수문자 이스케이프)로 검색어를 안전하게 만든다
    safe_kw = re.escape(keyword)

    # 해당 사용자 범위에서 텍스트에 키워드가 포함된 문서 검색(대소문자 무시/유니코드)
    cursor = collection.find(
        {"user_id": user_id, "text": {"$regex": safe_kw, "$options": "iu"}},
        {"_id": 0}  # _id 제외
    ).sort("timestamp", -1)  # 최신순 정렬

    # 이름 관련 키워드면 추가 패턴(“내 이름은~”, “~라고 해”)으로 확장 검색 --> 데모용 코드
    if keyword in ("이름", "성함", "호칭"):
        extra = collection.find(
            {
                "user_id": user_id,
                "text": {
                    # 이름 진술 패턴(둘 중 하나라도 매칭되면 OK)
                    "$regex": r"(?:내\s*이름\s*은|제\s*이름\s*은)|(?:[가-힣A-Za-z]+\s*(?:라고|이라|이야)\s*해)",
                    "$options": "iu"
                }
            },
            {"_id": 0}
        ).sort("timestamp", -1)
        # 기본 검색 + 확장 검색을 합치고, 각각 max_results 만큼만 취한다
        rows = list(cursor.limit(max_results)) + list(extra.limit(max_results))
    else:
        # 이름 관련이 아니면 기본 검색 결과만 사용
        rows = list(cursor.limit(max_results))

    # 점수(_score_row)와 타임스탬프를 기준으로 재정렬(우선순위 높은 순서로)
    rows.sort(key=lambda r: (_score_row(r.get("text", "")), _ts_key(r.get("timestamp", ""))), reverse=True)
    # 상위 max_results 개만 반환
    return rows[:max_results]

# ===== 감정 기반 기억 검색을 위한 휴리스틱 규칙 =====
# 질의 느낌의 문장(기억나/뭐였지/인가/일까/물음표 등) 탐지용 정규식
RE_QUERY = re.compile(r"(기억\s*나|기억해|뭐였지|인가|일까|\?)")
# 이름 선언 1: “내(제) 이름은 XXX” 패턴
RE_NAME_FACT1 = re.compile(r"(?:내|제)?\s*이름\s*은\s*[가-힣A-Za-z]+")
# 이름 선언 2: “XXX 라고/이라/이야 해” 패턴
RE_NAME_FACT2 = re.compile(r"[가-힣A-Za-z]+\s*(?:라고|이라|이야)\s*해")
# 선호/취향 관련 단서(좋아/싫어/선호/즐기/애정/바꾸/변경)
RE_PREF = re.compile(r"(좋아하|좋아해|싫어하|선호|즐기|애정|바꾸|변경)")

def _is_query(text: str) -> bool:
    # 문장 속에 질의 패턴이 하나라도 있으면 True
    return bool(RE_QUERY.search(text))

def _is_name_fact(text: str) -> bool:
    # 이름 진술 패턴(두 종류 중 하나라도) 매칭 시 True
    return bool(RE_NAME_FACT1.search(text) or RE_NAME_FACT2.search(text))

def _score_row(text: str) -> float:
    # 문장 중요도 점수 계산(이름 진술 가중치 ++, 선호 가중치 ++, 질문 성격은 가중치 --)
    s = 0.0
    if _is_name_fact(text):
        s += 5.0  # 이름 사실은 높은 가중치
    if RE_PREF.search(text):
        s += 3.0  # 취향 단서도 가중치
    if _is_query(text):
        s -= 4.0  # 질문 문장은 회상 사실로서 가중치 낮춤
    return s