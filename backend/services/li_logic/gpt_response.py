# gpt_response.py
# role: gpt 발화 모듈

# import modules
import openai
import os
import re
from backend.services.li_logic.ethics_filter import is_safe, suggest_rewrite
from datetime import datetime

# 디버그 모드: 프롬프트/중간로그를 출력할지 제어 .env에서 설정
DEBUG = os.getenv("LIRA_DEBUG", "0") == "1"

# env에서 OpenAI API 키를 가져온다.

# # 여기에 Upstage 발급 키를 넣는다
# openai.api_key = os.getenv("UPSTAGE_API_KEY")           
# openai.api_base = os.getenv("OPENAI_API_BASE", "https://api.upstage.ai/v1")

# 여기에 OPENAI 발급 키를 넣음
openai.api_key = os.getenv("OPENAI_API_KEY")           

# GPT API를 호출하고 응답을 반환하는 함수이다.
def call_gpt_api(prompt):
    """
    LLM 호출 후 assistant 메시지 content만 반환.
    """
    # 호출 시도(최대 2회: 최초 1회 + 실패 시 1회)
    for attempt in range(2):
        try:
            # ChatCompletion 엔드포인트(접속지점) 호출
            # -> message 배열로 기본규칙을 llm에게 보내준다.
            response = openai.ChatCompletion.create(
                # model=os.getenv("UPSTAGE_MODEL", "solar-pro2"),
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=[
                    # 입력토큰 : 리라의 기본규칙
                    {"role": "system", "content": (
                        "당신은 감정을 이해하고 기억하는 AI '리라'입니다.\n\n"
                        "[규칙]\n"
                        "1) 모든 응답은 한국어로 시작하며, 한 문장으로 간결히 답하세요 (최대 이모지 1개).\n"
                        "2) 단순 회상(이름/취향/사실)은 짧게 단정형으로만 답하고, 프롬프트 해설은 금지합니다.\n"
                        "3) 따옴표(\\\"“”'')는 사용하지 않습니다.\n"
                        "4) 기억이 충돌하면 최신 타임스탬프의 정보를 진실로 간주합니다.\n"
                        "5) 저장 트리거(예: '기억해')나 사실 명시가 있으면 모호하더라도 단정형으로 답합니다.\n"
                        "6) 해당 주제와 관련된 기억이 하나라도 있으면 ‘모르겠어요’를 말하지 않고 단정형으로 답합니다.\n"
                        "7) 관련 기억이 전혀 없을 때만 추측 없이 모르겠어요 라고 답합니다.\n"
                        "8) 기억·메모 응답에서는 기억했습니다/기억하겠습니다/저장 완료 등 저장 관련 문구를 절대 쓰지 않습니다. 사실만 말합니다.\n"
                        "9) 날짜, 점수, 감정 라벨, 내부 키/ID, 저장 여부 등 메타데이터는 출력하지 않습니다.\n"
                        "10) 규칙이 애매하면 간결함을 우선합니다.\n"
                        "11) 사용자의 감정(label·score)에 맞춰 톤을 조절하고, 공감하는 듯한 말투로 답합니다."
                    )},
                    # 사용자 메시지
                    {"role": "user", "content": prompt}
                ],
                # llm의 응답토큰 제한 개수 : 1024토큰 (모델이 생성할 수 있는 최대 토큰 수)
                # 주의! : 다른 토큰 개수와는 별개 설정이다.
                max_tokens=1024,

                # 창의성 및 정확성 균형 (낮을수록 사실 전달 성향이 강해짐)
                # 0.0 ~ 0.3 -> 사실 전달·정확성 중시.
                # 0.4 ~ 0.7 -> 정확성과 자연스러움의 균형.
                # 0.8 ~ 1.2 -> 창의적인 글쓰기, 아이디어 발산.
                # 1.3 ~ 2.0 -> 매우 자유롭고 예측 불가능.
                temperature=0.1,

                # 네트워크 지연/모델 응답 지연에 대한 타임아웃(초)
                request_timeout=20,
            )
            # 메시지 객체 전체가 아닌, content 텍스트만 반환
            # 예시
            """ 
                # response.choices =
                # [
                #     {
                #         "index": 0,
                #         "message": { "role": "assistant", "content": "안녕하세요!" },
                #         "finish_reason": "stop"
                #     },
                #     {
                #         "index": 1,
                #         "message": { "role": "assistant", "content": "반가워요, 오늘 하루 어땠나요?" },
                #         "finish_reason": "stop"
                #     },
                #     {...}   
                # ]
            """
            # 상기의 인덱스 0만을 리턴 -> 대화 맥락 유지
            return response.choices[0].message["content"]
        
        # 예외처리
        except Exception as e:
            # 디버그 모드에서 에러 메시지 출력
            if DEBUG:
                print(f"[GPT] 호출 실패 (attempt {attempt+1}): {e}")
            # 첫 시도 실패 시, 1회만 재시도
            if attempt == 0:
                continue
            # 최종 실패 시, 사용자 친화 기본 응답 반환(UX 보호)
            return "잠시 응답이 지연되고 있어요. 다시 한 번 시도해 볼게요."

# 이 함수는 사용자의 감정, 기억, 입력을 기반으로 GPT 모델에 전달할 프롬프트를 생성한다.
# STM(이전 대화)과 LTM(회상된 기억)을 모두 사용하여 LLM을 위한 최종 프롬프트를 구성.
def build_prompt(user_input: str, emotion: dict, recalled_ltm: list, stm_data: dict) -> str:
    # 1. STM에서 과거 대화 기록을 가져온다.
    lines = []
    for turn in stm_data.get("chat_history", []):
        line = f"{turn['role']}: {turn['content']}"
        lines.append(line)

    chat_history_block = "\n".join(lines)
    """
        # 예시: stm_data chat_history내부 구조
        stm_data = {
            "chat_history": [
                {"role": "user", "content": "안녕 리라야!"},
                {"role": "lira", "content": "안녕하세요! 반가워요 :)"},
                {"role": "user", "content": "오늘 날씨 어때?"},
                {"role": "lira", "content": "오늘은 맑고 따뜻해요."}
            ]
        }

        # 위 코드를 거친 후, chat_history_block 결과:
        chat_history_block = 
            user: 안녕 리라야!
            lira: 안녕하세요! 반가워요 :)
            user: 오늘 날씨 어때?
            lira: 오늘은 맑고 따뜻해요.
    """
    # 2. STM의 LTM 버퍼와, 방금 회상한 LTM을 합친다.
    # 예시:
    #   1. 중복된 내용이 있는 STM과 LTM을 합친다.
    #   유저 입력: "너의 이름은 뭐니?"
    #   [과거 대화 기록-STM]
    #     STM: "내 이름은 현 우야"
    #     STM: "내 이름은 현우야" -> 중복내용
    #           +
    #    [참고할 기억들-LTM]
    #     LTM: (2025-08-17 03:59) 안 녕
    #     LTM: (2025-08-17 03:57) 안녕 -> 중복내용
      
    #   2. 중복된 공백 및 대소문자를 무시하고 필터링한다.
    #   유저 입력: "너의 이름은 뭐니?"
    #   [과거 대화 기록-STM]
    #     STM: "내 이름은 현우야"
    #     STM: "내 이름은 현우야" -> 중복내용
    #    [참고할 기억들-LTM]
    #     LTM: (2025-08-17 03:59) 안녕
    #     LTM: (2025-08-17 03:57) 안녕 -> 중복내용
    
    #   3. 중복된 내용이 확인되면 -> 첫 번째 항목만 append,
    #      이후 중복 항목은 무시된다.
    #   유저 입력: "너의 이름은 뭐니?"
    #   [과거 대화 기록-STM]
    #     STM: "내 이름은 현우야" -> append
    #     STM: "내 이름은 현우야" -> 중복내용
    #    [참고할 기억들-LTM]
    #     LTM: (2025-08-17 03:59) 안녕 -> append
    #     LTM: (2025-08-17 03:57) 안녕 -> 중복내용
    
    # 요약:
    # - STM/LTM에서 가져온 항목을 '프롬프트에 넣기 직전' 하나의 리스트로 합친 뒤,
    #   공백/대소문자 무시 기준으로 중복을 제거한다(첫 번째 항목만 유지). -> 최신이건 이전이건 상관없이 중복된 공백 및 대소문자를 무시하고 필터링한다.
    # - 이 과정은 출력용 포맷팅 단계이며, 원본 STM/LTM 저장소의 데이터는 변경하지 않는다.

    # LTM(대부분 타임스탬프 보유) -> STM 버퍼(대개 텍스트만) 순서로 합친다.
    # 같은 문장이 두 소스에 모두 있을 때, 앞에 온 항목이 유지되므로
    # 타임스탬프가 있는 LTM 항목이 우선 보존되도록 한다.
    all_recalled_memories = (recalled_ltm or []) + (stm_data.get("recalled_ltm_buffer", []) or [])

    # --- 타임스탬프 기준으로 최신 먼저 정렬(없으면 뒤로) ---
    def _get_dt_for_sort(m):
        """
        프롬프트 표시에 쓸 '정렬용' 타임스탬프 파싱.
        - datetime / ISO 문자열(Z 포함) / epoch 숫자 다 받아줌
        - 없거나 실패하면 None -> 정렬 시 뒤로 밀림
        - 반환되는 datetime은 UTC 타임존 정보가 포함된 aware 객체로 통일
        """
        from datetime import timezone
        ts = m.get("timestamp") or m.get("saved_at") or m.get("created_at") or m.get("ts")
        try:
            if isinstance(ts, datetime):
                dt = ts
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            if isinstance(ts, str) and ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    return dt
                except ValueError:
                    return None
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts, timezone.utc)
        except Exception:
            return None
        return None

    from datetime import timezone
    _FALLBACK_MIN = datetime.min.replace(tzinfo=timezone.utc)

    # 정렬 규칙:
    # 1) 타임스탬프가 있는 항목 우선
    # 2) 그 안에서는 타임스탬프 내림차순(최신이 맨 위)
    # 3) 타임스탬프가 없는 항목은 리스트 뒤쪽으로 밀림
    all_recalled_memories = sorted(
        all_recalled_memories,
        key=lambda m: ( _get_dt_for_sort(m) is not None, _get_dt_for_sort(m) or _FALLBACK_MIN ),
        reverse=True
    )

    # 예시의 2~3단계에서 사용할 key 집합
    seen = set()
    # 프롬프트에 들어갈 LTM 라인들
    memory_lines = []
    # 1단계: (정렬 완료) + 중복 제거 하면서 라인 만들기
    for m in all_recalled_memories:
        text = m.get("text", "")
        # 빈 문자열/공백만 있는 경우는 프롬프트에서 제외 (노이즈 제거)
        if not text or not text.strip():
            continue
        # 2단계: 공백/대소문자 무시
        key = re.sub(r"\s+", "", text).lower()
        # 3단계: 중복이면 스킵... append는 memory_lines.append(f"- {timestamp_str}{text}")로 처리
        if key in seen:
            continue                                      # 중복이면 스킵
        seen.add(key)

        # --- 타임스탬프를 프롬프트에 포함 (가능할 때만 표시) ---
        # 원칙:
        # 1) 실제 저장 시각이 있을 때만 보여준다 (없으면 비워둠)
        # 2) 문자열 ISO / epoch / datetime 다 받아줌
        # 3) now()로 채우는 일은 절대 안 함 (오해 방지)
        timestamp_str = ""
        ts = m.get("timestamp")  # timestamp 는 datetime / str(ISO) / epoch / None 가능
        dt = None
        try:
            from datetime import timezone

            # 1) datetime 객체
            if isinstance(ts, datetime):
                dt = ts

            # 2) 문자열 ISO (Z 포함 허용)
            elif isinstance(ts, str) and ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    dt = None

            # 3) epoch(초) 숫자
            elif isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts, timezone.utc)

            # 4) 대체 필드(saved_at/created_at/ts) 탐색 (동일 규칙)
            if dt is None:
                alt = m.get("saved_at") or m.get("created_at") or m.get("ts")
                if isinstance(alt, datetime):
                    dt = alt
                elif isinstance(alt, str) and alt:
                    try:
                        dt = datetime.fromisoformat(alt.replace("Z", "+00:00"))
                    except ValueError:
                        dt = None
                elif isinstance(alt, (int, float)):
                    dt = datetime.fromtimestamp(alt, timezone.utc)

            # 5) 최종 포맷팅: 유효한 dt가 있을 때만 프롬프트에 표시
            if dt is not None:
                # tz-aware 는 그대로, naive 는 그대로 출력 (내부 저장 시점 기준)
                timestamp_str = f"({dt.strftime('%Y-%m-%d %H:%M:%S')}) "
        except Exception:
            # 어떤 이유로든 처리 실패 시 타임스탬프는 생략
            timestamp_str = ""

        # 최종 한 줄 형태로 구성
        memory_lines.append(f"- {timestamp_str}{text}")

    # LTM 블록이 비어있으면 안내 문구로 대체
    memory_block = "\n".join(memory_lines) if memory_lines else "(참고할 특정 기억 없음)"

    # 3. 모든 정보를 종합하여 최종 프롬프트를 생성한다.
    #    - 최신 정보 우선 규칙을 시스템 지시에 명시
    #    - 주제 정합성 규칙을 통해 환각, 논리비약을 억제
    # 리라의 회상규칙
    return f"""다음은 사용자와의 대화입니다.

[대화 기록 - 최근(Short-term)]
{chat_history_block}

[회상된 기억 - 장기(Long-term)]
{memory_block}

[사용자 감정 상태]
감정: {emotion['label']}, 감정강도(점수): {round(emotion['score'], 2)}

[현재 대화]
사용자: {user_input}
리라:"""

# 양끝을 감싸고 있는 따옴표 쌍("...", ‘...’, '...')만 제거하는 함수.
def _strip_wrapping_quotes(text: str) -> str:
    # 입력된 문자열에서 양쪽 감싸고 있는 따옴표("”, '' 등)을 제거한다.
    # 양끝이 "쌍을 이뤄" 감싸진 경우에만 제거한다.
    #       앞뒤 문자가 다르거나 한쪽만 있는 경우는 원문을 유지.
    # - text가 none일 경우 ""로 대체 후 strip()으로 앞뒤 공백 제거
    t = (text or "").strip()
    
    # 제거할 따옴표 쌍 후보 목록
    pairs = [("\"","\""), ('“','”'), ("'","'")]
    
    # 문자열이 해당 쌍으로 시작/끝나는지 확인
    for l, r in pairs:
        if t.startswith(l) and t.endswith(r):
            # 양 끝의 따옴표를 제거하고 strip()으로 다시 공백 제거
            return t[1:-1].strip()
    
    # 따옴표로 감싸져 있지 않다면 원문 그대로 반환
    return t

# 한글이 포함된 응답만 후처리(따옴표 제거/어미 다듬기/공백 정리)
def _sanitize_korean_reply(text: str) -> str:    
    if re.search(r'[가-힣]', text):
        # 모든 종류의 따옴표 문자 제거
        text = re.sub(r'[\"\'“”]', '', text)
        # 문장 어미를 조금 더 대화체로 보정
        text = re.sub(r'였습니다\.', '예요.', text)
        text = re.sub(r'입니다\.', '예요.', text)
        # 앞뒤 여백 제거
        text = text.strip()
    return text

# 최종 응답 생성 함수
def generate_response(prompt):
    # 디버그 로그: 프롬프트가 그대로 출력되므로 운영환경에서는 비활성/마스킹 권장
    if DEBUG:
        print(prompt)

    # 1) 모델 호출
    reply = call_gpt_api(prompt)

    # 2) 양끝 따옴표 제거
    reply = _strip_wrapping_quotes(reply)

    # 3) 한국어 문장 후처리(따옴표/어미/공백) – 가독성만 살짝 개선
    reply = _sanitize_korean_reply(reply)

    # 4) 안전 필터 (부적절 출력 시 대체 문구)
    if not is_safe(reply):
        reply = suggest_rewrite()
    # 5) 회신
    return reply