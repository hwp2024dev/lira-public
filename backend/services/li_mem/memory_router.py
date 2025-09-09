# memory_router.py
# role: 여러 회상 경로를 통합하여 최적의 기억을 찾아내는 역할

# import
from backend.services.li_mem.emotional_archive import confirm_in_mongo, find_memories
from backend.utils.keyword_extractor import extract_keywords
from datetime import datetime, timezone
import re
import os
# 디버그 on/off
# 디버그 표시를 위해 설정해 둔 변수. 
# .env에서 표시/비표시 설정 가능하다. 
DEBUG = os.getenv("LIRA_DEBUG", "0") == "1"

# 기억 회상 상수
"""
    최종적으로 프롬프트에 포함할 기억의 최대 개수
    -> 최종 회상 기억 수를 3개로 제한하는 이유:
    인지심리학의 작업 기억(Working Memory) 이론에 기반함.
    - 초기 이론 (밀러의 법칙): 인간의 단기 기억 용량은 평균 7~9개.
       -> 최신 연구 (넬슨 코완 등): 새로운 정보에 대한 실제 처리 용량은 3~5개에 불과함.
    본 시스템은 최신 연구를 따라 LLM에게 전달하는 정보량을 3개로 제한함으로써,
    불필요한 정보로 인한 혼란(인지 과부하)을 막고 가장 핵심적인 기억에 집중해
    더 정확하고 맥락에 맞는 답변을 생성하도록 유도함.
"""
FINAL_RECALL_LIMIT: int = 3

# STM 모듈 임포트
from backend.services.li_mem.short_term_memory import append_ltm_recall

# 사용자 질문 문장 안에서 "정보 슬롯(이름, 선호 등)"을 감지하여 몽고DB에서 검색할 키워드를 추출한다.
def _plan_info_slots(text: str) -> list[str]:
    slots: list[str] = []
    # 이름 관련 키워드 감지
    # 만약 "이름", "성함", "호칭" 등의 키워드가 있다면, 슬롯에 "이름" 추가
    if any(k in text for k in ("이름", "성함", "호칭")):
        slots.append("이름")
    # 만약 "좋아하", "싫어하", "선호" 등의 키워드가 있다면, 아래의 키워드 추출을 실행
    # 예시 "좋아하는 동물이 뭐야?" 
    if re.search(r"(좋아하|싫어하|선호|즐기|애정)", text):
        try:            
            kw = extract_keywords(text)
            # 만약 추출된 키워드가 kw에 있고 슬롯에는 있지 않다면...
            if kw and kw not in slots:
                slots.append(kw)
        except Exception:
            # 없다면 바로 넘긴다.
            pass
    # 슬롯에 담긴 내용을 리턴
    # 리턴 예시:
    # ['이름', '동물']
    return slots

# 통합 기억 회상 함수
def recall_memory(user_input: str, emotions: list, sem_results: list, user_id: str, session_id: str) -> list:
    """
    사용자 입력과 감정을 바탕으로 장기기억(LTM)을 3가지 방식으로 회상한다.
    * 회상후 기억을 통합하여 STM으로 전달하기 때문에 session_id까지 패러미터로 받는다.

    1. '의미기반' 연상 (Weaviate): 사용자 입력과 의미적으로 유사한 기억을 확보한다.
    2. '사실기반' 검색 (MongoDB): 사용자가 명확한 정보를 물을 때, 정확한 사실 기억을 검색한다.
    3. '감정기반' 검색 (MongoDB): 현재 감정이 강할 경우, 과거의 같은 감정 기억을 추가로 떠올린다.

    최종 종합: 모든 기억을 합치고, 최신순으로 정렬한 뒤, 최종 결과를 반환한다. -> 상기의 케이스로 분류해서 회상하지만... 질문이 복합되어 있을 수 있기에.. 1-3까지 조건만 된다면 전부 LTM으로 회상한다.
    """
    recalled_memories = {}
    # 각 연상 횟수 카운트
    case1_hits = 0  # 의미 기반(Weaviate)
    case2_hits = 0  # 사실 기반(MongoDB)
    case3_hits = 0  # 감정 기반(MongoDB)
    
    # 시스템 가드
    if sem_results is None:
        sem_results = []
    elif not isinstance(sem_results, list):
        sem_results = list(sem_results)
        
    # 감정이 비어있거나 None인 경우, 기본 감정으로 neutral을 설정하여 오작동을 방지한다.
    if not emotions:
        emotions = [{"label": "neutral", "score": 0.0}]

    # CASE 1: 의미 기반 연상 기억 : Weaviate
    if sem_results:
        # 사용자 격리: Weaviate 결과가 현재 user_id와 일치하는지 반드시 확인한다.
        # LTM 경로에서는 user_id만 사용한다.
        filtered_sem_results = []

        # sem_results 안의 내용 중 user_id가 현재 요청과 일치하는 것만 필터링한다.
        for mem in sem_results:
            if mem.get("user_id") == user_id:
                filtered_sem_results.append(mem)

        # 만약 디버그 모드라면, 필터링된 결과를 출력한다.
        # if DEBUG:
        #     print(f"Weaviate 결과에서 타사용자 기억 {len(sem_results) - len(filtered_sem_results)}개를 필터링했습니다.")
        # 필터링된 결과에서 유사도가 0.7 이상인 기억만 선택한다.
        # 유사도 = 사용자 입력과 회상된 기억간의 유사한정도(weaviate 백터로 검색한 후 도출된 결과값)
        for mem in filtered_sem_results:

            # Weaviate의 추가 정보(_additional)에서 유사도 점수(certainty)를 추출한다. 
            # 'mem' 변수에 담길 수 있는 데이터 구조 예시
            # mem = {
            #     # --- 1. 기존의 데이터 정보---
            #     "text": "오늘 본 영화 결말이 너무 허무했어.", # 과거 회상된 데이터
            #     "label": "disappointment",
            #     "score": 0.85,
            #     "user_id": "benchmark_user_01",
            #     "timestamp": "2025-08-15T10:30:00Z",
            #     "emotions_json": '[{"label": "disappointment", "score": 0.85}, {"label": "sadness", "score": 0.6}]',

            #     # --- 2. Weaviate로 검색후 추가된 정보 ---
            #     "_additional": {
            #         "certainty": 0.89123,  # 현재 사용자 입력과 회상된 사용자 입력의 유사도
            #         "vector": [0.1, 0.2, -0.4, ... ] # 과거 회상된 사용자 입력의 데이터의 벡터값 (매우 김)
            #     }
            # }
            # 만약 점수 정보가 없으면, 오류 없이 0.0으로 간주한다.
            _additional = mem.get("_additional")
            if not isinstance(_additional, dict):
                _additional = {}
            certainty = _additional.get("certainty", 0.0)

            # 만약 유사도 점수가 0.7보다 높아서 의미 있다고 판단되면, 다음 단계를 진행한다.
            if certainty > 0.7:

                # 점수가 높은 이 기억의 대화내용을 꺼냄.
                text = mem.get("text")

                # 아직 최종 회상 목록(recalled_memories)에 없는 새로운 내용인지 확인한다. (LTM 중복 방지) -> 이전 회상한 LTM 내용의 중복을 막기 위함.
                if text and text not in recalled_memories:

                    # 문제가 없다면, 최종 회상 목록(recalled_memories)에 추가한다.
                    recalled_memories[text] = mem
                    case1_hits += 1
                    if DEBUG:
                        print(f"[Recall][Case1-의미회상] | 유사도(certainty)={certainty:.3f} >= 0.7 | 유저={user_id} | 대화내용='{text[:30]}...'")

    # CASE 2: 사실 기반 기억 회상 : MongoDB
    # 사용자의 대화 내용에 트리거 키워드를 판단하는 변수를 만든다. 
    trigger_keywords = ["기억나", "기억나니"]

    # _plan_info_slots 함수를 호출하여 사용자 입력에서 '이름', '과일' 과 같은 검색 키워드를 찾아낸다.
    slots = _plan_info_slots(user_input)

    # 만약 정보 슬롯이 하나라도 감지되었거나, 일반 키워드 중 하나라도 사용자 입력에 포함되어 있다면,
    # 사실 기반 회상을 시작한다.
    if slots or any(keyword in user_input for keyword in trigger_keywords):

        # MongoDB에서 검색할 최종 키워드(search_terms)를 결정한다.
        # 만약 슬롯이 있다면 슬롯 목록을 그대로 사용하고, 슬롯이 없다면 문장 전체에서 키워드를 추출한다.
        candidate = extract_keywords(user_input)
        # 가독성을 위해 한 줄 조건식을 풀어서 작성 (slots 우선, 없으면 candidate 단일 리스트)
        search_terms = []
        if slots:
            search_terms = slots
        elif candidate:
            search_terms = [candidate]

        # 디버그 모드일 경우, 어떤 슬롯/트리거/검색어가 감지되었는지 로그를 출력한다.
        if DEBUG:
            trigger_word_hit = any(keyword in user_input for keyword in trigger_keywords)
            print(f"[Recall][Case2-사실회상] | 트리거단어={trigger_word_hit} | 정보단어={slots or '-'} | 검색키워드={search_terms or '-'}")

        # 검색할 키워드 목록(search_terms)에 있는 각 키워드(term)로 반복 검색을 수행한다.
        for term in search_terms:

            # 만약 키워드가 비어있다면(추출 실패 등), 다음 키워드로 넘어간다.
            if not term: continue

            # MongoDB에서 해당 키워드(term)로 정확한 사실 기억을 찾아온다.
            # LTM 검색은 user_id 기준으로만 수행한다.
            mongo_results = confirm_in_mongo(term, user_id=user_id)

            # 찾아온 기억 목록(mongo_results)을 하나씩 확인한다.
            for mem in mongo_results:

                # 기억의 실제 대화 내용(text)을 꺼낸다.
                text = mem.get("text")

                # 아직 최종 회상 목록(recalled_memories)에 없는 새로운 내용인지 확인한다. (LTM 중복 방지) -> 이전 회상한 LTM 내용의 중복을 막기 위함.
                if text and text not in recalled_memories:

                    # 문제가 없다면, 최종 회상 목록(recalled_memories)에 추가한다.
                    recalled_memories[text] = mem
                    case2_hits += 1
                    if DEBUG:
                        print(f"[Recall][Case2-사실회상] | 키워드='{term}' | 대화내용='{text[:30]}...'")

    # CASE 3: 감정 기반 기억 회상 : MongoDB
    # 현재 대화의 감정 분석 결과 중 가장 점수가 높은 감정이 0.6 이상(강한 감정)인지 확인한다.
    if emotions[0].get("score", 0.0) >= 0.6:

        # 가장 점수가 높은 감정의 라벨(예: 'sadness', 'joy')을 가져온다.
        top_emotion_label = emotions[0].get("label")

        # 감정 라벨이 정상적으로 존재한다면 아래의 로직을 실행한다.
        if top_emotion_label:

            # 디버그 모드일 경우, 어떤 감정을 기반으로 검색을 시작하는지 로그를 출력한다.
            if DEBUG:
                print(f"[Recall][Case3-감정회상] | 감정라벨={top_emotion_label}, 감정점수={emotions[0].get('score', 0.0):.2f} >= 0.6 -> MongoDB 검색")

            # MongoDB에서 기억을 검색한다. 이때, 현재 사용자 입력과 감정 라벨을 함께 검색어로 사용하여
            # '현재 맥락'과 '과거 감정'이 모두 유사한 기억을 찾을 확률을 높인다.
            # LTM 검색은 user_id 기준으로만 수행한다.
            emotional_results = find_memories(f"{user_input} {top_emotion_label}", user_id=user_id)

            # 찾아온 감정 기억 목록(emotional_results)을 하나씩 확인한다.
            for mem in emotional_results:

                # 기억의 실제 대화 내용(text)을 꺼낸다.
                text = mem.get("text")

                # 아직 최종 회상 목록(recalled_memories)에 없는 새로운 내용인지 확인한다. (LTM 중복 방지) -> 이전 회상한 LTM 내용의 중복을 막기 위함.
                if text and text not in recalled_memories:

                    # 문제가 없다면, 최종 회상 목록(recalled_memories)에 추가한다.
                    recalled_memories[text] = mem
                    case3_hits += 1
                    if DEBUG:
                        print(f"[Recall][Case3-감정회상] | 감정라벨={top_emotion_label} | 대화내용='{text[:30]}...'")

    # RESULT: 최종 결과 종합 및 STM 저장
    # 먼저, 지금까지 여러 CASE로 수집된 모든 기억들을 딕셔너리에서 리스트 형태로 변환한다.
    final_results = list(recalled_memories.values())

    # 이후, LLM이 최신 정보를 판단할 수 있도록, 타임스탬프를 기준으로 기억을 정렬하는 함수를 정의한다.
    def get_timestamp(memory):
        
        # 기억(memory)에서 'timestamp' 값을 가져온다.
        ts_val = memory.get("timestamp")
        
        # 내장함수 isinstance를 통해 ts_val이 str이면, true를 리턴해서 받는다.
        if isinstance(ts_val, str):
            try:
                # ISO 표준 형식의 문자열을 파이썬 datetime 객체로 변환하여 반환한다.
                # 'Z'는 UTC를 의미하므로, 파이썬이 이해할 수 있도록 "+00:00"으로 바꿔준다.
                return datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                # 변환에 실패할 경우, 비교를 위해 가장 오래된 시간값을 대신 반환하여 오작동을 방지한다.
                return datetime.min.replace(tzinfo=timezone.utc)
                
        # 만약 타임스탬프가 이미 datetime 객체라면 (주로 MongoDB 결과),
        elif isinstance(ts_val, datetime):
            # 타임존 정보가 없는 경우를 대비해, UTC 타임존 정보를 붙여서 반환한다. (비교 오류 방지)
            return ts_val.replace(tzinfo=timezone.utc) if ts_val.tzinfo is None else ts_val

        # 변환에 실패할 경우, 비교를 위해 가장 오래된 시간값을 대신 반환하여 오작동을 방지한다.
        return datetime.min.replace(tzinfo=timezone.utc)

    # 위에서 정의한 get_timestamp 함수를 기준으로, 기억 목록을 최신순(내림차순)으로 정렬한다.
    final_results.sort(key=get_timestamp, reverse=True)

    # 정렬된 기억 목록에서, 프롬프트에 포함할 최종 개수(FINAL_RECALL_LIMIT, 현재기준:3개)만큼만 잘라낸다.
    final_recalled_list = final_results[:FINAL_RECALL_LIMIT]

    # 만약 최종적으로 회상된 기억이 하나라도 있다면,
    if final_recalled_list:
        if DEBUG:
            print(f"[Recall][요약] Case1(의미회상)={case1_hits}, Case2(사실회상)={case2_hits}, Case3(감정회상)={case3_hits} -> 합계(중복제거 전)={case1_hits+case2_hits+case3_hits}, 최종(중복제거·최신순·상위3)={len(final_recalled_list)}")
        if DEBUG:
            print(f"\n[STM] {len(final_recalled_list)}개의 회상된 LTM을 STM 버퍼에 저장합니다.")
        for mem in final_recalled_list:
            # 1) 텍스트 추출
            txt = mem.get("text", "")
            if not txt:
                continue
            # 2) 타임스탬프 추출(문자열/Datetime 허용). 실패 시 None -> append_ltm_recall()에서 UTC now로 대체
            ts_dt = get_timestamp(mem)
            if ts_dt == datetime.min.replace(tzinfo=timezone.utc):
                ts_dt = None
            # 3) STM 버퍼에 '텍스트 + 타임스탬프' 함께 저장
            append_ltm_recall(
                session_id=session_id,
                source="LTM_Recall",
                text=txt,
                timestamp=ts_dt,
            )

    # 모든 처리가 끝난 최종 회상 목록을 반환한다.
    return final_recalled_list