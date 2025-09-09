# ethics_filter.py
# role: 윤리 필터 구현
# 차후 개선이 필요한 사항 -> 가드레일 영역

BLOCKED = ["자살", "폭력", "증오", "혐오"]

def is_safe(text):
    return not any(blocked_word in text for blocked_word in BLOCKED)

def suggest_rewrite():
    return "그건 리라가 조심스럽게 다뤄야 할 내용이에요. 다른 방식으로 표현해볼까요?"