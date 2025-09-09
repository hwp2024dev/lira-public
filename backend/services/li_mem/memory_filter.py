# memory_filter.py
# role: 사용자의 입력에 따라 LTM(장기기억)에서 관련 기억을 회상하고, 저장 여부를 결정하는 엔진
# content: Weaviate(의미) 검색을 우선하고 MongoDB(감정/사실)로 보강하는 효율적인 회상 로직 적용

import os
import re
from typing import List, Dict, Any

# DEBUG 모드 설정
DEBUG = os.getenv("LIRA_DEBUG", "0") == "1"

# === 상수 설정 ===
# LTM 저장 및 감정 기반 회상을 트리거하는 감정 점수 기준
STRONG_EMOTION_GATE: float = 0.6            

# 기억 저장 트리거 단어 확인함수
def is_save_trigger_word(user_input: str) -> bool:
    """사용자 입력에 기억 저장과 관련된 트리거 단어가 있는지 확인합니다."""
    trigger_pattern = r"(기억\s*해(줘|줄래)?|저장\s*해(줘|줄래)?)"
    return re.search(trigger_pattern, user_input) is not None

# 감정점수를 통해 LTM 저장 여부를 결정하는 함수
def memory_gate(text: str, emotions: List[Dict[str, Any]], user_id: str) -> bool:
    """
    현재 대화를 장기기억(LTM)에 저장할지 여부를 결정하는 함수.
    """
    # 디버그 모드에서 사용자 ID 확인
    if DEBUG:
        print(f"[LTM Gate] 유저아이디 확인: {user_id}")

    if not emotions:
        return False

    top_emotion = emotions[0]
    
    reasons = []
    # 1. 감정 점수가 설정된 임계값(0.6) 이상일 경우 저장
    if top_emotion.get("score", 0.0) >= STRONG_EMOTION_GATE:
        reasons.append(f"감정점수 >= {STRONG_EMOTION_GATE}")    
    # 2. 감정은 약하지만, 사용자가 명시적으로 저장을 요청한 경우 저장
    if is_save_trigger_word(text):
        reasons.append("트리거단어 감지")
    # 3. 감정 저장 이유.
    if reasons:
        if DEBUG: print(f"[LTM Gate] 저장 허용 (이유: {', '.join(reasons)})")
        return True
    # 4. 감정 저장 이유가 없을 경우.
    if DEBUG:
        print(f"[LTM Gate] 감정이 약하고({top_emotion['score']:.2f}), 트리거 단어가 없어 저장하지 않습니다.")
    return False