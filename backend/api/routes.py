# routes.py
# role : FastAPI 라우터의 지휘부이자 관제탑
# content: main.py에서 정의된 FastAPI 앱의 /generate 요청을 처리

# LTM 검색은 user_id 기준, STM 격리는 session_id 기준 -> 사용자 단위 일관성 보장
#   - 현재 포폴용으로는 클라나 터미널 입력에서 user_id와 session_id를 함께 받아오는 방식사용 중
#   - 추후 개선 방향: 아래의 내용을 기준으로 보안패치를 진행할 예정
# =====================================================
# user_id vs session_id 정리
# 
# user_id (UUID, 영구 ID)
# - 회원가입 시 서버가 발급하는 고유 식별자
# - JWT 토큰 안에 포함 -> 인증/인가 기준
# - LTM(Mongo/Weaviate) 저장/조회 시 "사람 단위"로 사용
# - 주민등록번호처럼 평생 변하지 않는 고유값(LTM DB에 영구저장)
#
# session_id (UUID, 일회용 ID)
# - 로그인 후 대화 세션 시작 시 서버가 발급
# - Redis(STM) 저장/조회 시 "세션 단위"로 사용
# - TTL이 끝나면 자동 소멸
# - 카페 진동벨처럼 일시적인 번호표(STM에 통합시 발급후 초기화시 삭제됨)
#
# user_id와 session_id를 같이 들고 가기는 하지만, 
# LTM에 저장시 user_id만 저장하여 무결성을 챙기고
# STM에 저장시 session_id만 저장하여 대화 세션 단위로 기억을 분리한다.
# 
# 정리:
#   - LTM = user_id 기준 (사람 단위로 기억 지속/영구)
#   - STM = session_id 기준 (대화 세션별로 기억 분리/일회성)
#   - user_id/session_id 혼용 저장은 기억 오염을 유발 -> 반드시 역할에 맞게 분리 사용(LTM에 혼용사용시 무결성이 깨짐)
# =====================================================
import os

# 1.라우터 관련 모듈 임포트
from fastapi import APIRouter
from pydantic import BaseModel

# 2.감정 분석 서비스 모듈 임포트
from backend.services.li_emo.emotion_engine import analyze_emotion
from backend.services.li_mem.memory_router import recall_memory
from backend.services.li_mem.memory_filter import memory_gate
from backend.services.li_mem.emotional_archive import store_memory
from backend.services.li_logic.prompt_engine import run_lira_response

# 2-1. 단기기억(STM) 모듈 임포트 
from backend.services.li_mem.short_term_memory import get_session_memory, append_chat_history

# 2-2. 의미기반 장기기억(LTM) 저장소 모듈 임포트
from backend.services.li_mem.semantic_archive import store_semantic_memory

# 2-2-1. 의미기반 장기기억(LTM) 검색 함수 임포트
from backend.services.li_mem.semantic_archive import search_semantic_memory

# 2-3. 감정분석 내용을 표 형식 출력용 모듈 임포트
from tabulate import tabulate
from datetime import datetime
from datetime import timezone

# 2-4. 기타 임포트 모듈
import re

# 디버그 플래그 환경변수로 설정
DEBUG = os.getenv("LIRA_DEBUG", "0") == "1"

# 3.라우터 인스턴스 로드
router = APIRouter()

# 4.타임스탬프 표준화 함수
# 역할: 다양한 형식의 타임스탬프 입력을 타임존 정보가 없는 UTC datetime으로 변환하여 반환.
# 변환이유 : 각 처리 모듈에서 받는 타임스탬프의 형식이 다를 수 있기 때문에 데이터 표에서 출력전에 통일된 형식으로 변환해준다.

# --- 다양한 형식의 타임스탬프 형식 ---
# 타임존 정보가 있는 timestamp
# "2025-08-11T12:33:32+09:00"
# "2025-08-11T03:33:32Z"
# "datetime(2025,8,11,3,33,32,tzinfo=timezone.utc)"

# --- 변환하고자 하는 타임스탬프 형식 ---
# 타임존 정보가 없는 timestamp
# 아래의 형식으로 통일 시키고자 함.
# -> 2025-08-11 03:33:32
def normalize_timestamp(ts):
    if ts is None:
        return datetime.min
    # --- Case 1: datetime 객체가 이미 들어온 경우 ---
    if isinstance(ts, datetime):
        # 타임존 정보가 없으면 그대로 반환
        if ts.tzinfo is None:
            return ts
        # 타임존 정보가 있으면 UTC로 변환 후 타임존 정보 제거한다.
        return ts.astimezone(timezone.utc).replace(tzinfo=None)

    # --- Case 2: 문자열 형태로 들어온 경우 ---
    # 문자열 변환 + 양쪽 공백 제거
    s = str(ts).strip()
    # 빈 문자열인 경우 최소값 반환
    # 이유 : 변환할 날짜 정보가 없을 때 에러를 피하기 위해 가장 작은 날짜값 (0001-01-01 00:00:00)을 넣어서 오름, 내림 차순의 오류를 방지한다.
    # 만약 파싱처리한 후에 빈 문자열이 들어오면, 가장 작은 날짜값을 넣어서 오류를 방지한다.
    if not s:
        return datetime.min
    
    # 'Z'로 끝나는 형식(UTC)을 Python ISO 포맷 호환 형태로 변환
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # ISO 형식으로 파싱 시도, 실패 시 최소 날짜 반환
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return datetime.min
    
    # 타임존 정보가 있으면 UTC로 변환 후 제거후 타임존 정보가 없는 timestamp형식으로 반환
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

# 5. 데이터 표 형식 결과 산출 (터미널 출력용)
# 역할 : 회상된 기억 리스트를 사람이 보기 좋게 표 형태로 출력한다.
# 이유 : 디버깅과 개발 과정에서 기억 내용, 감정, 점수, 타임스탬프를 직관적으로 확인하기 위함.
# 출력 예시 : Text(대화 내용), Label(감정), Score(강도), Timestamp(시간)
def print_table(memories: list[dict], user_input: str = "", user_emotions: list[dict] = None):
# --- STEP 1: 사용자 입력과 감정 출력 ---
    if user_input:
        print("사용자 입력:")
        print(user_input)
    if user_emotions:
        print("\n사용자 감정:")
        for e in user_emotions:
            print(f"{e['label']}: {round(e['score'], 3)}")

# --- STEP 2: 정렬 키 함수 정의 ---
# 이유 : memories(회상된 사용자 입력)을 최신순으로 정렬하기 위해 timestamp 값을 비교 가능하게 변환.
    def sort_key(x):
        ts = x.get("timestamp", "")
        if isinstance(ts, datetime):
            return ts
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return datetime.min

    # --- STEP 3: timestamp 표준화 ---
    # 이유 : aware/naive datetime 비교 오류를 방지하고 모두 naive UTC로 통일
    # 이전 작성해 둔, 4.타임스탬프 표준화 함수(normalize_timestamp)를 사용하여 timestamp를 UTC로 표준화한다. -> 표의 오름/내림차순을 하여 사용자 입력의 최신성을 알기위함
    for m in memories:
        ts = m.get("timestamp") or m.get("created_at") or m.get("updated_at")
        m["timestamp"] = normalize_timestamp(ts)

    # --- STEP 4: 최신순 정렬(내림차순) ---
    memories = sorted(memories, key=sort_key, reverse=True)

    # --- STEP 5: 표 출력 데이터 구성 ---
    table = []
    for m in memories:
        # Text: 30자 초과 시 말줄임(...) 처리
        text = m.get("text", "")[:30] + "..." if len(m.get("text", "")) > 30 else m.get("text", "")

        # label과 score가 없는 경우, emotions에서 최고 감정 추출
        label = m.get("label", "")
        score = m.get("score", "")
        if (not label or label == "") or (not score or score == ""):
            emotions = m.get("emotions", [])
            if emotions:
                top_emotion = sorted(emotions, key=lambda x: x.get("score", 0), reverse=True)[0]
                label = top_emotion.get("label", "")
                score = round(top_emotion.get("score", 0), 3)

        # Timestamp: 문자열 변환
        timestamp = str(m.get("timestamp", "")) if "timestamp" in m else ""

        # 표에 한 줄 추가
        table.append([text, label, score, timestamp])

    # --- STEP 6: 표 출력 ---
    # 이유 : tabulate 라이브러리를 사용하여 표 형태로 출력한다.
    print("\n회상된 기억(Timestamp 내림차순):")
    print(tabulate(table, headers=["Text", "Label", "Score", "Timestamp"], tablefmt="fancy_grid"))
# 출력은 아래의 예시처럼 작동한다.
# 회상된 기억:
# ╒════════════════════════════════════════════════════════╤═════════╤═════════╤═══════════╕
# │ Text                                                   │ Label   │   Score │ Timestamp │
# ╞════════════════════════════════════════════════════════╪═════════╪═════════╪═══════════╡
# │ 기억해줘. 너 덕분에 오늘 하루가 진짜 따뜻했어.                    │ neutral │   0.572 │2025-07-31 04:54:44.543000     │
# ├────────────────────────────────────────────────────────┼─────────┼─────────┼───────────┤
# │ 기억해줘... 나 요즘 계속 불안해서 숨쉬는 것도 힘들...             │ neutral │   0.755 │2025-07-29 04:54:44.543000     │
# ├────────────────────────────────────────────────────────┼─────────┼─────────┼───────────┤
# │ 리라야, 오늘 너무 좋은 하루였어. 너랑 이야기하면서 ...             │ joy     │   0.871 │2025-07-26 04:54:44.543000     │
# ╘════════════════════════════════════════════════════════╧═════════╧═════════╧═══════════╛

# 5.pydantic 기반 입력 데이터 모델 정의
# 역할: 사용자입력(채팅)으로 받은 JSON의 'text' 필드를 자동으로 추출 + 유효성 검사
# "text"라는 키가 없거나 str이 아니면 자동 422 오류를 리턴해줌
# 쉽게 말하자면 사용자 입력의 양식을 정의하고 유효성 검사까지 해주는 역할
class TextInput(BaseModel):
    text: str

# 이후에는 def generate() 함수의 매개변수로 의존성 주입되어 아래의 함수에 전달됨
# -> def generate(request: TextInput) -> 아래에 존재하는 함수

# 위 클래스(TextInput)는 유효성 검사를 자동으로 수행한 후,
# request 변수에 TextInput 타입의 인스턴스로 자동 주입함
# “예를 들면... FastAPI가 내부적으로 만들어주는 값 예시는 아래와 같다.”
# -> request = TextInput(text="오늘 기분이 좋네")

# 6.사용자 입력에 따른 메모리 저장 및 회상 (POST / generate 요청처리)
# -> post방식으로 /generate라는 url로 요청이 들어오면 이 함수를 실행시킨다는 뜻
# -> FastAPI의 데코레이터 문법을 사용한 것

# 6-1.그리고 사용자의 입력을 받으면
# @아래 함수를 작동시켜라 장치("감정을 분석해라 주문(주소)가 들어가면...")
# def 감정분석 장치실행():
#     return "감정 분석 결과 리턴" -> 리턴값은 json임. 자세한건 emotion_engine.py의 analyze_emotion() 함수 참고
#     --> emotion_engine.py의 analyze_emotion(request.text)로 실행시키고 값을 리턴받음

# --- Pydantic 모델을 API 엔드포인트보다 먼저정의 ---
# 클라에서 받은 유저/세션 아이디를 그대로 담아주는 임시 구조 -> 보안패치 예정(상세내용은 line5 참조)
class LiraRequest(BaseModel):
    user_id: str
    session_id: str
    text: str

# 아래 함수 부터는 사용자 입력을 받고, 뇌의 작동을 모방하여 작동한다.
@router.post("/generate")
def generate(request: LiraRequest):
    """
    사용자 입력을 받아 Lira의 응답을 생성하고, 대화의 단기/장기기억을 총괄 관리한다.
    """
    # user_id, session_id확인
    if DEBUG:
        print(f"[사용자정보 확인] user_id={request.user_id} session_id={request.session_id}")
    # --- STEP 1: STM(단기기억) 로드 ---
    if DEBUG:
        print(f"\n[STM] Loading STM for session: {request.session_id}")
    # 세션 ID를 기반으로 Redis(STM)에서 현재 대화의 단기기억을 불러온다.    
    stm_data = get_session_memory(request.session_id)

    # --- STEP 2: 감정 분석 ---
    if DEBUG:
        print("\n[1. 사용자 입력 및 감정 요약] [감각 피질 + 변연계]")
    # analyze_emotion 함수로 사용자의 입력 텍스트를 분석하여 감정 점수를 분류한다.    
    all_emotions = analyze_emotion(request.text)

    # analyze_emotion() 예시 반환 형태
    # ---------------------------------------------------
    # 1) threshold(감정강도 : 0.3 -> 함수의 패러미터에 설정된 값) 이상인 감정이 여러 개일 경우 -> 상위 3개 반환
    # #  threshold: 감정의 최소 강도 점수 (0.3 이상만 유의미하다고 판단하여 설정).
    # [
    #     {"label": "joy", "score": 0.872},
    #     {"label": "sadness", "score": 0.351},
    #     {"label": "surprise", "score": 0.342}
    # ]
    #
    # 2) threshold 이상인 감정이 1~2개일 경우 -> 그 개수만큼 반환
    # [
    #     {"label": "neutral", "score": 0.566}
    # ]
    #
    # 3) threshold 이상인 감정이 전혀 없을 경우 -> 점수가 가장 높은 감정 1개
    # [
    #     {"label": "neutral", "score": 0.212}
    # ]
    #
    #    항상 최소 1개의 감정이 리스트로 반환됨
    #    (감정명: 영어, score: 0~1 사이 실수)
    # ---------------------------------------------------

    # 감정 분석 결과를 정렬하여 가장 강한 감정부터 출력한다.
    # 리턴받은 값의 score를 기준으로 내림차순 정렬
    user_emotions = sorted(all_emotions, key=lambda x: x['score'], reverse=True)
    if not user_emotions:
        user_emotions = [{"label": "neutral", "score": 0.0}]
    if DEBUG:
        print(f"사용자 입력:{request.text}")
        print("사용자 감정:")
        for e in user_emotions:
            print(f"  {e['label']}: {round(e['score'], 3)}")
    # 예시 출력:
    # 사용자 입력:안녕하세요, 오늘 날씨가 너무 좋네요!
    # 사용자 감정:
    #   joy: 0.872
    #   sadness: 0.351
    #   surprise: 0.342

    # --- STEP 3: LTM(장기기억) 회상 준비 및 실행 ---
    # 역할: 사용자의 입력(감정, 키워드)에 따라 LTM(weaviate,mongoDB)에서 관련 기억을 찾아내고, 그 결과를 STM(redis) 버퍼에 저장.
    
    # 기억회상 트리거 준비
    # 기본값 설정
    sem_results: list = []
    # 먼저, 채팅내용에 "기억나?" 또는 "기억나니?"라는 트리거 단어가 포함된 경우, 의미 기반회상(weaviate)을 생략한다. 
    # -> 이 경우 사실기반 검색(MongoDB)을 통해 정보성 사실(감정x)만 회상한다. -> 이후 STM에 저장
    trigger_re = re.compile(r"(기억나(?:니)?\??)")
    is_trigger = bool(trigger_re.search(request.text))

    # 키워드 트리거(기억나?, 기억나니?)가 아닐 때, 의미기반 검색(Weaviate)을 통해 감정 사실을 회상한다. -> 이후 STM에 저장
    # 키워드 트리거는 아래의 search_semantic_memory() 함수의 실행 가/부만 결정한다. 다른뜻은 없음.
    if not is_trigger:
        if DEBUG:
            print("\n[2. 의미기반 유사문장 회상 결과][연합피질]")
            print("[prepare_semantic_memory] weaviate에서 저장된 기억의 파편(벡터) 검색중...")

        # search_semantic_memory에서 cohere로 임베딩된 벡터를 사용하여 weaviate에 저장된 내용을 검색(의미기반 검색)한다.
        sem_results = []
        sem_results = search_semantic_memory(request.text, user_id=request.user_id)

        # sem_results = 
        # 리스트로 반환하여 변환(top_k = 3개만 검색했기에 3개만 반환된다.)
        # [
        #   {
        #     "text": "기억해줘. 나 요즘 너무 힘들어.",
        #     "label": "sadness",
        #     "score": 0.711,
        #     "timestamp": "2025-07-24T11:13:27.456789Z",
        #     "_additional": {
        #       "certainty": 0.874
        #     }
        #   },
        #   {...}
        #   {...}
        # ]

    # 검색 백터를 통한 LTM 회상 실행 및 STM 버퍼링
    if DEBUG:
        print("\n[3. LTM 회상 및 STM 버퍼링][해마 + 측두엽]")

    try:
        # recall_memory()는 다음과 같은 회상을 실행한다.
        """
        LTM Recall Pipeline (직렬 실행, 조건 충족 시 누적)

        세션 사용 원칙: LTM 검색은 user_id 기준, session_id는 STM 세션 격리 용도로 사용한다.

        실행 순서: 의미 회상 -> 사실 회상 -> 감정 회상 -> LTM 회상통합/LTM 회상정렬(타임스탬프 순)/LTM 회상 최대3개 추출

        CASE 1: 의미 기반 회상
        - 조건: '기억나 / 기억나니' 트리거가 없는 경우에만 실행
        - 방식: Weaviate에서 현재 입력과 의미적으로 유사한 기억을 검색
               · 동일 user_id만 사용
               · 유사도(certainty) >= 0.7만 채택
        - 효과: 감정/문맥이 가까운 과거 발화를 먼저 떠올림

        CASE 2: 사실 기반 회상
        - 조건(둘 중 하나라도 참):
               ① 사용자 입력에 트리거 단어가 있음 (기억나 / 기억나니)
               ② 정보 슬롯 감지(예: '이름', '선호' 등) 또는 문장 키워드 추출 결과 존재
        - 방식: MongoDB에서 키워드/슬롯 기반으로 정확한 사실성 기억 검색
               · 동일 user_id만 사용
        - 효과: 이름/선호/사실 질의에 대해 정확한 값 회수

        CASE 3: 감정 기반 회상 보강
        - 조건: 최상위 감정 강도 >= 0.6
        - 방식: 현재 user_input + 감정 라벨을 합쳐 MongoDB 검색
               · 동일감정 라벨이 담긴 과거 기억을 보강
               · 동일 user_id만 사용
        - 효과: 강한 감정 상황에서 정서적으로 일치하는 맥락을 추가

        통합 규칙
        - 중복 방지: 텍스트 기준으로 중복 제거
        - 정렬: timestamp 기준 최신순
        - 제한: 상위 3개(FINAL_RECALL_LIMIT)만 반환

        후속 처리
        - 반환된 회상은 STM(Redis) 버퍼에 기록하여 프롬프트에 사용
        - '저장'은 별도 게이트에서 판단(감정 >= 0.6 또는 '기억해줘' 요청) 후
          MongoDB/Weaviate에 적재하며, 회상과는 독립적으로 동작
        """
        recalled_ltm = recall_memory(
            user_input=request.text, # 사용자 입력
            emotions=user_emotions,  # 감정 분석 결과
            sem_results=sem_results, # 의미 검색 결과
            user_id=request.user_id, # 사용자 ID
            session_id=request.session_id  # STM 저장을 위해 (임시:보안개선 예정 - 클라에서 받은)session_id 전달
        )
    except Exception as e:
        if DEBUG:
            # 인자를 잘못 받았을 경우 출력
            print(f"[ERROR] recall_memory 호출 실패: {e}")
            # 500 오류(서버 내부에 예상치 못한 문제 발생) 방지를 위해 recalled_ltm에 빈 리스트를 할당하여 방지
            print("[WARN] 500 오류(프리징) 방지를 위해 빈 recalled_ltm으로 계속 진행합니다.")
        recalled_ltm = []

    # --- STEP 4: LTM(장기기억) 저장 ---
    # 역할: 현재 대화가 LTM으로 저장될 가치가 있는지 판단하고, 저장.
    if DEBUG:
        print("\n[4. 기억 저장][편도체 + 해마]")

    if memory_gate(request.text, user_emotions, user_id=request.user_id):
        """
        memory_gate() 함수에서 0.6 이상의 감정 or 트리거단어(기억,저장)을 받은경우, LTM에 저장할 수 있도록 한다.
        이후 상기의 저장여부(가/부)가 작동했을경우, 리턴값을 True로 반환하고 store_memory(), store_semantic_memory() 함수를 실행시킨다.
        """  
        if DEBUG:
            print("[LTM] 사용자 입력이 메모리에 기록되고 있음 (Mongo/Weaviate)...")
        # 현재 양방향에 동시에 저장 하는 이유는 weaviate는 의미 기반 검색에 최적화되어 있고, MongoDB는 사실 기반 검색에 최적화되어 있기 때문.
        # MongoDB에 저장
        store_memory(
            user_id=request.user_id,
            text=request.text,
            emotions=user_emotions
        )
        # Weaviate에 저장
        store_semantic_memory(
            user_id=request.user_id,
            text=request.text,
            emotions=user_emotions
        )
        if DEBUG:
            print("memory 저장 완료")
    else:
        if DEBUG:
            print("memory gate 통과 실패 -> 기억 저장 안함")

    # --- STEP 5: 회상된 기억 출력 ---
    if DEBUG:
        print("\n[5. 회상기억 출력][후두엽 + 언어피질]")
        # 회상된 기억을 표 형태로 출력한다. 
        print_table(recalled_ltm, request.text, user_emotions)

    # --- STEP 6: 최종 응답 생성 ---
    # 역할: STM(과거 대화)과 LTM(회상된 기억)을 모두 고려하여 최종 답변을 만든다.
    if DEBUG:
        print("\n[CORE] Generating final response...")
    # STM과 LTM을 모두 종합하여 최종 프롬프트를 만들고, reply함수는 generate_response함수를 통해 LLM(발화GPT) 응답을 생성한다.
    reply = run_lira_response(
        user_input=request.text,
        user_emotions=user_emotions,
        # 방금 LTM에서 회상한 기억
        recalled_ltm=recalled_ltm,
        # Redis에서 불러온 단기기억 (과거 대화 등)
        stm_data=stm_data          
    )

    # --- STEP 7: STM(단기기억) 업데이트 ---
    # 역할: 방금 나눈 대화를 다음을 위해 단기기억에 기록.
    if DEBUG:
        print("\n[STM] Appending current turn to Short-Term Memory...")
    # 현재 세션의 STM에 사용자 입력과 Lira의 응답을 추가한다.    
    append_chat_history(session_id=request.session_id, role="user", content=request.text)
    append_chat_history(session_id=request.session_id, role="lira", content=reply)

    # --- STEP 8: 프론트엔드로 결과 반환 ---
    if DEBUG:
        print("\n[API] Sending response to client.")
    # 최종 응답을 JSON 형태로 반환하여 프론트엔드에서 원하는 형태로 보내준다.
    return {
        "output": reply,
        "emotion": {
            "emotion_1st_label": user_emotions[0]["label"],
            "emotion_1st_score": user_emotions[0]["score"],
            "emotion_2nd_label": user_emotions[1]["label"] if len(user_emotions) > 1 else None,
            "emotion_2nd_score": user_emotions[1]["score"] if len(user_emotions) > 1 else None,
            "emotion_3rd_label": user_emotions[2]["label"] if len(user_emotions) > 2 else None,
            "emotion_3rd_score": user_emotions[2]["score"] if len(user_emotions) > 2 else None,
            "emotion_mode": "central" # 추후 감정모드(central, peripheral)로 구분하여, 전달할 수 있도록 세팅 (기능 확장용)
        }
    }