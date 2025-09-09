# backend/services/li_logic/prompt_engine.py
# 역할 : 사용자 입력에 대한 GPT 응답을 생성하는 프롬프트를 구성하는 모듈.

#import modules
from typing import List, Dict, Any

# gpt_response 모듈의 함수들이 이제 stm_data를 처리한다.
from backend.services.li_logic.gpt_response import generate_response, build_prompt

# STM과 LTM을 모두 종합하여 최종 프롬프트를 만든다.
def run_lira_response(
    user_input: str,
    user_emotions: List[Dict[str, Any]],
    recalled_ltm: List[Dict[str, Any]],
    stm_data: Dict[str, Any],
) -> str:

    # 감정 없을 때의 에러 방지 안전 가드
    # build_prompt()에서 감정 데이터를 쓰기 때문에, 최소 한 개의 감정 정보는 반드시 있어야 한다.
    emotion = user_emotions[0] if user_emotions else {"label": "neutral", "score": 0.0}

    # 프롬프트 폭주 방지: 회상된 LTM이 과도하게 길어지는 것을 막기 위해 상한 적용
    # 필요 시 20~50 사이 조정 가능. 현재 50으로 설정. -> 경험적 테스트 결과, 50이 적당하다고 판단.
    MAX_LTM = 50
    recalled_ltm_capped = recalled_ltm[:MAX_LTM]

    # build_prompt 함수에 stm_data를 전달
    prompt = build_prompt(
        user_input=user_input,
        emotion=emotion,
        recalled_ltm=recalled_ltm_capped,
        stm_data=stm_data
    )
    # 생성한 프롬프트를 generate_response 함수 호출에 넣고 리턴
    return generate_response(prompt)