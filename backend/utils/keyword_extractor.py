# keyword_extractor.py
# role: 핵심 키워드 추출기
# content: 사용자 입력 문장에서 Mongo 검색에 유리한 "핵심 토큰"을 안정적으로 추출한다.
# 설명:
#  - 동사/형용사도 검색 토큰으로 쓰기 위해 '명사화 규칙' 적용 (예: 좋아하다->좋아, 싫어하다->싫어, ~하다->어간)
#  - 동사/형용사는 표면형을 우선 사용 (고정 설정)

# import modules
import re
import os
from typing import List

# 1) kiwipiepy (설치 필수)
# 형태소 분석기 사용. 미설치 시 즉시 오류로 안내하여 정확도 저하를 방지한다.
try:
    from kiwipiepy import Kiwi
except ImportError:
    raise RuntimeError(
        "[keyword_extractor] 'kiwipiepy' 모듈이 설치되어 있지 않습니다. "
        "다음 명령으로 설치 후 다시 실행하세요: pip install kiwipiepy"
    )

# 디버그 플래그: 전역(LIRA_DEBUG) 설정에 따라 활성화
# 로컬의 .env 파일에서 LIRA_DEBUG 값을 0,1로 설정 가능

DEBUG_KEYWORD = (os.getenv("LIRA_DEBUG", "0")) == "0"
# 전역 Kiwi 인스턴스(재사용) — 매 호출마다 새로 생성하지 않고 모듈 로드 시 1회만 생성
_KIWI = Kiwi()

# -----------------------------
# 전처리 & 공통 리소스 정의
# -----------------------------

# 한국어/영문/숫자 토큰 추출을 위한 정규식 감지세팅
_KOREAN_KEEP = re.compile(r"[가-힣0-9a-zA-Z]+")

# 사용자 호출(봇 호명) 및 자기지시 어구 제거용 패턴
_SELF_CALL_PATTERNS = [
    r"^\s*리라(야|여)?[\s,]*",  # "리라야", "리라여"
    r"^\s*hey\s*lira[\s,]*",
    r"^\s*hi\s*lira[\s,]*",
    r"^\s*hello\s*lira[\s,]*",
]
_SELF_REFERENTIAL_TOKENS = {"리라", "lira", "어시스턴트", "assistant", "챗봇", "bot"}

# 조사/접속/형식 명사 계열(형태소 단계에서 대부분 걸러지나 안전장치)
_STOPWORDS = set([
    "이", "그", "저", "것", "거", "수", "등", "및", "또", "또는", "그리고", "하지만",
    "그래서", "즉", "혹은", "요", "네", "응", "음", "아", "어", "에", "은", "는", "이요",
    "내", "제", "저의", "것들", "거기", "여기",
])

# 대화 슬롯 힌트(핵심 엔티티 단어)는 우선 랭크
_SLOT_HINTS = ("이름","커피","동물","반려동물","색","취향","강아지","고양이","선호","기호","색상")

# 검색 토큰으로 쓸 품사
_ALLOWED_TAGS = {
    # 명사류
    "NNG", "NNP", "NNB", "NR", "NP",
    # 동사/형용사 계열
    "VV", "VA", "VX", "VCN",
    # 일반부사, 접속부사          
    "MAG", "MAJ",                     
}

# 키워드 점수화 규칙
# -> 규칙을 둔 이유 : 몽고DB 검색시, 중요 키워드를 우선순위로 가져오기 위함
# -> 나, 너, 저 등 대명사/의문사 계열보다는 선호, 비선호 표현이 우선순위가 높아야 키워드를 선정하기 쉽다.

# 페널티 토큰: 대명사/의문사 계열
_MINUS_SCORE_TOKENS = {"나", "너", "내", "제", "저", "그대", "당신", "뭐", "무엇", "거", "것", "기억", "나요", "니", "어디", "언제", "누구"}

_PLUS_SCORE_TOKENS = (
    "좋",  # 좋아(하다)
    "싫",  # 싫어(하다)
    "선호",
    "애정",
    "즐기",
    "관심",
    "바꾸",  # 바꾸다/바꿀게
    "변경",
    "정정",
    "교체",
)

# 감정/예의 표현(검색 핵심어로 부적절) — 랭킹 페널티 대상
_EMOTION_ONLY_TOKENS = {
    "미안", "미안해", "미안하",
    "사과", "죄송",
    "고마워", "고맙",
    "감사", "감사하"
}

# (질문/회상 맥락 힌트)를 추출하기 위한 정규식 감지세팅
_RE_RECALL = re.compile(r"(기억\s*나|기억\s*하|기억해|기억해줄|기억해\s*줘)")

# 가장 낮은 점수 (키워드 검색어 후보중에 의미없는 것을 탈락 시키기 위함)
LOWEST_SCORE = -99999

# -----------------------------
# 키워드 추출 유틸 함수
# -----------------------------
# 어절 단위의 원문 문자열을 추출
def _extract_eojeol_from(text: str, start: int) -> str:
    # start 인덱스부터 끝까지 잘라서 tail이라는 새 문자열을 만든다.
    tail = text[start:]
    m = re.match(r"[가-힣0-9a-zA-Z]+", tail)

    return m.group(0) if m else ""

# 표제어/표면형을 검색 토큰으로 변환하는 함수
""" 패러미터 설명(내용 확인을 원치 않으면 접기)
    # 1. surface: str
    # 형태소의 “표면형”.
    # 예) 문장 “막혀서 힘들다” 에서 surface="막혀서"

    # 2. lemma: str
    # 표제어(원형). 활용(변형) 풀어놓은 기본형.
    # 예) surface="막혀서" -> lemma="막히다", surface="좋아해" -> lemma="좋아하다"
    # 참고: Kiwi 구버전에서는 없을 수 있어서 코드에서 getattr() or surface로 안전하게 다룸.

    # 3. tag: str
    # 품사 태그(키위 표기).
    # 예) NNG(일반명사), NNP(고유명사), VV(동사), VA(형용사), MAG(일반부사) 등.
    # 이 값으로 “동사 or 형용사냐?”를 판단해서 처리 분기를 탄다.

    # 4. text: str
    # 전체 원문 문장.
    # 동사/형용사일 때 표면형을 어절 단위로 다시 뽑아 쓰는 로직에서 활용됨(문맥 기반 정규화).

    # 5. start: int
    # 이 형태소가 문장 text 안에서 시작하는 인덱스
    # text[start:]로 꼬리 부분 잘라서 어절 추출(_extract_eojeol_from)에 사용.
    # 예) text="막혀서 힘들다"에서 "막혀서"가 인덱스:0, "힘들다"가 인덱스:4 같은 식으로 처리.

    # 6. prefer_surface_for_verbs: bool = True
    # 동사/형용사(VV/VA 등)일 때 무엇을 토큰으로 쓸지 결정하는 스위치.

    # 6-1. True(기본): 표면형(문장에 나온 형태) 우선.
    # 예) "막혀서" 그대로 쓰거나, 어절 추출해 정규화해서 사용.
    # -> 문맥 신호(어미/활용)가 검색에 도움 될 때 유리.

    # 6-2. False: 표제어 기반 명사화 규칙 적용.
    # 예) "좋아하다"->"좋아", "싫어하다"->"싫어", "...하다"->어간
    # -> 검색 키워드를 더 일반화/정규화하고 싶을 때 유리.
"""
def _normalize_token(surface: str, lemma: str, tag: str, text: str, start: int, prefer_surface_for_verbs: bool = True) -> str:

    # 표면 전처리 (불필요 기호 제거)
    surface_norm = "".join(_KOREAN_KEEP.findall(surface)).lower()
    # 표제어 전처리 (불필요 기호 제거)
    lemma_norm = "".join(_KOREAN_KEEP.findall(lemma or surface)).lower()

    # 표제어 전처리가 있으면 그걸쓰고 없으면 표현형을 쓴다. 
    token = lemma_norm or surface_norm

    # 토큰이 비어있거나(None or 빈 문자열) 블용어 목록(_STOPWORDS)에 있으면 빈 문자열 반환
    if not token or token in _STOPWORDS:
        return ""
    # 토큰 길이가 2보다 작으면 빈 문자열 반환
    if len(token) < 2:
        return ""

    # V 계열 처리 : 한국어 형태소 태그(키위/세종 계열)에서 동사 형용사 보조용언 부정지정사처럼 '어미 변형'을 하는 서술어류
    # -> VV/VA/VX/VCN 같은 'V'로 시작하는 품사만 여기로 들어온다.
    # -> VV 동사, VA 형용사, VX 보조용언, VCN 부정지정사
    # -> 동사/형용사는 기본적으로 "문장에 나온 모양(표면형)"을 우선 키워드로 쓴다.

    # 품사 태그가 V로 시작하면(V계열이면)
    if tag.startswith("V"):
        # 동사/형용사를 표면형(원문에 보이는 형태)으로 우선사용한다면,(패러미터 설정 : prefer_surface_for_verbs=True)
        if prefer_surface_for_verbs:
            # 표면형에서 어절 단위로 추출
            eo = _extract_eojeol_from(text, start)
            # 어절에서 한글/영문/숫자만 추출하고 소문자화
            token = "".join(_KOREAN_KEEP.findall(eo)).lower() or surface_norm
        else:
            # - "...하다"로 끝나면
            if token.endswith("하다"):
                # 예) "좋아하다" -> "좋아"
                token = token[:-2]
            # - "...다"로 끝나면           
            if token.endswith("다"):
                # 예) "가다" -> "가"
                token = token[:-1]
        # 안전장치: 비거나 한 글자면 토큰 취소
        if not token or len(token) < 2:
            return ""
        # 여기서 바로 반환 — 동사/형용사는 위 규칙으로 끝낸다.
        return token
    # VV/VA 계열이 아니면(명사(NN), 부사(MA), 수사(NR) 같은 비(非)동사계열) 그대로 반환
    # VV/VA가 아니면 키워드 검색시 큰 문제가 없음
    # 예시 : "사람" -> "사람", "아주" -> "아주"
    # 자기지시/봇호명 토큰은 검색에서 제외
    if token in _SELF_REFERENTIAL_TOKENS:
        return ""
    return token

# tokens_with_tags: List[(token, tag)], text: str
# 후보 토큰들을 점수와 빈도로 정렬하여 중복 없는 토큰 리스트로 반환
def _rank_tokens(tokens_with_tags: List[tuple[str, str]], text: str) -> List[str]:
    """
    주어진 (토큰, 품사) 후보 리스트를 바탕으로, 각 토큰의 중요도 점수와 빈도를 계산하여
    최종 키워드 순위를 결정하고, 중복 없는 리스트로 반환한다.

    패러미터:
        tokens_with_tags: (토큰, 품사) 형태의 튜플 리스트.
        text: 원문 텍스트 (점수 계산 시 맥락을 파악하는 데 사용).

    리턴값:
        점수와 빈도 순으로 내림차순 정렬된, 중복 없는 최종 키워드 리스트.
    """
    # 후보군이 없으면 빈 리스트를 반환하여 불필요한 연산을 방지.
    if not tokens_with_tags:
        return []

    # 1. 후보 토큰 집계 및 점수/빈도 계산 ---
    # can_token 딕셔너리는 각 후보 토큰의 정보를 집계하는 역할을 한다.
    # 예: {('커피', 'NNG'): {'freq': 2, 'score': 3.5}}
    can_token = {}
    for tok, tag in tokens_with_tags:
        # 비어있는 토큰은 무시.
        if not tok:
            continue
        
        # (토큰, 품사)를 고유 키로 사용하여 동일한 단어라도 품사가 다르면 별도로 집계한다.
        key = (tok, tag)

        # 키가 처음 등장하는 경우, 빈도와 점수를 0으로 초기화.
        can_token.setdefault(key, {"freq": 0, "score": 0.0})

        # 1-1. 빈도(freq) 계산: 토큰이 등장할 때마다 빈도를 1씩 증가.
        can_token[key]["freq"] += 1

        # 1-2. 점수(score) 계산: 같은 토큰이 여러 번 등장해도 가장 높게 계산된 점수만 유지한다.
        #      이를 통해, 어쩌다 한번 낮은 점수를 받더라도 그 토큰의 최대 중요도는 유지된다.
        can_token[key]["score"] = max(
            can_token[key]["score"],
            _score_token(tok, tag, text)
        )

    # 2. 점수와 빈도 기준으로 최종 순위 결정
    # 집계된 토큰들을 정렬하여 최종 순위를 산출.
    ranked = sorted(
        can_token.items(),
        # 정렬 기준: 1순위는 '점수(score)', 2순위는 '빈도(freq)'
        # 파이썬의 튜플 정렬(lambda) 특성에 따라, 점수가 높은 순으로 먼저 정렬되고,
        # 점수가 동일할 경우 빈도가 높은 것이 더 앞 순위를 차지하게 된다.
        key=lambda x: (x[1]["score"], x[1]["freq"]),
        # 내림차순(True)으로 정렬하여 가장 중요한 키워드가 맨 위로 오게 한다.
        reverse=True
    )

    # 3. 중복 제거 및 최종 리스트 생성
    # 정렬된 순서는 유지하되, 동일한 토큰이 여러 품사로 순위에 올랐을 경우 한 번만 포함시킨다.
    seen = set()  # 이미 추가된 토큰을 빠르게 확인하기 위한 set
    result = []   # 최종 결과를 담을 리스트
    
    # ranked 리스트를 순회하며 최종 키워드를 추출.
    # 예: [ (('커피', 'NNG'), {'score': 3.5, 'freq': 2}), (('좋아', 'VV'), {'score': 2.8, 'freq': 1}), ... ]
    for (tok, tag), _ in ranked:
        # 비어있거나 이미 추가된 토큰은 건너뛴다.
        if not tok or tok in seen:
            continue

        # 새로운 토큰을 seen set과 result 리스트에 추가한다.
        seen.add(tok)
        result.append(tok)
        
    return result

# 길이/빈도 기반에 맥락 가중치(부스트/페널티)를 더해 점수를 만든다.
def _score_token(token: str, tag: str, text: str) -> float:

    # 1. 토큰이 없으면(빈 문자열 등) 가장 낮은 마이너스 점수로 반환 (후보에서 탈락)
    if not token:
        # 가장 낮은 점수로 설정
        return LOWEST_SCORE

    """
        가중치 점수는 개발중 경험을 기반으로 설정한 값들이다. chatGPT와 조정하여 결정한 점수.
    """
    # 2. 기본 점수: 1.0 + 토큰 길이의 10%만큼 가중치 줌
    # -> 토큰이 길수록(정보량 많을수록) 살짝 더 점수 높아짐
    base = 1.0 + len(token) * 0.1
    # 명사 우선 가중치: 일반명사/고유명사 우대
    if tag and tag.startswith("NN"):
        base += 0.8  # 명사 기본 가중치
        if tag == "NNP":
            base += 0.6  # 고유명사 추가 가중치

    # 3. 동사/형용사 계열에서 감정·상태 의미(힘들, 괜찮아 등)는 소폭 페널티
    # -> 너무 일반적인 동사/형용사는 명사로 후보가 가도록 유도
    if tag and tag.startswith("V") and token in {"힘들", "괜찮아", "괜찮", "되", "하다", "막히"}:
        base -= 0.4

    # 감정/예의 전용 표현은 핵심 검색어로 부적합하므로 추가 페널티
    if token in _EMOTION_ONLY_TOKENS:
        base -= 1.0

    # 4. 한 글자 토큰(예: "나", "것" 등)은 잡음일 확률이 높기에, 강한 페널티
    if len(token) < 2:
        base -= 2.0

    # 5. 동사/형용사 계열(V*)는 과도한 우선순위를 주지 않음 (명사 우선 정책)
    if tag and tag.startswith("V"):
        base += 0.1


    # 7. 특정 토큰(선호/비선호 계열)이면 추가 부스트
    # 예시: "좋아", "싫어", "선호", "즐기", "관심" 등은 점수 +0.5
    for pref in _PLUS_SCORE_TOKENS:
        if token.startswith(pref):
            base += 0.5  # 선호/비선호 신호는 유지하되 과도한 우선순위는 제한
            break
    # 변경/정정 의도가 문장에 있으면 슬롯 힌트 엔티티(이름/커피 등)에 약간의 추가 가중치
    if re.search(r"(바꾸|변경|정정|바꿀게|바꿔)", text):
        if token in {"이름", "커피", "취향"}:
            base += 0.6
    # 슬롯 힌트(핵심 엔티티)가 들어간 토큰은 강하게 가산
    if any(h == token or (len(token) >= 2 and h in token) for h in _SLOT_HINTS):
        base += 2.0

    # 8. 대명사/의문사 계열(나, 너, 저, 뭐 등)은 점수를 대폭 마이너스
    if token in _MINUS_SCORE_TOKENS:
        base -= 2.0

    # 9. 회상 맥락(문장에 "기억나?" 등)이면 "기억", "나" 계열은 추가로 더 감점
    # -> "기억", "기억나", "기억해", "기억하", "나" 등은 -3.0
    if _RE_RECALL.search(text):
        if token == "나" or token.startswith("기억"):
            base -= 3.0

    # 10. 최종 점수 반환
    return base

# -----------------------------
# 메인 API
# -----------------------------
#
# Returns: str when top_n==1, else List[str] - 한 문장에 추출된 하나 또는 여러 개의 의미단어 키워드 (Mongo 검색 토큰)
def extract_keywords(text: str, top_n: int = 1):

# 데이터 처리 흐름 :
# 1) kiwi로 형태소 분석 -> 허용 품사만 추출 -> 표제어화/명사화 규칙 적용 -> 토큰 후보 생성
# 2) 후보가 없으면 간단 규칙 기반 백업 사용
# 3) 최종 1개 토큰 반환(빈 경우 "")

    try:
        # 입력이 비어있으면 바로 반환
        # text.strip()으로 공백만 있는 경우도 처리
        if not text or not text.strip():
            if DEBUG_KEYWORD:
                # 원문 비어있을때 반환
                print(f"[keyword] input: {text}")
            # 키워드 없을때 반환
            return ""

        # 봇 호명/자기지시 접두부 제거 (키워드 쪼개짐 방지)
        cleaned = text
        for pat in _SELF_CALL_PATTERNS:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
        text = cleaned

        # 분석 대상이 되는 문장을 출력 해준다.
        if DEBUG_KEYWORD:
            print(f"[keyword] input: {text}")
        
        # (토큰, 태그) 후보군 저장 리스트.
        candidates: List[tuple] = []

        # ---- kiwi 형태소 분석으로 1차 후보 생성 ----
        # 전역 _KIWI 인스턴스를 재사용
        analyzed = _KIWI.analyze(text, top_n=1)
        
        if DEBUG_KEYWORD:
            # analyzed에 키워드 추출 결과가 들어 있으면, True, 아니면 False
            print(f"[keyword] kiwi.analyze -> has_result: {bool(analyzed)}")
        
        # 분석 결과가 있으면
        if analyzed:
            # 분석 결과의 첫번째 문장만 사용
            # morphemes : 형태소라는 뜻으로... 변수명을 지정
            morphemes = analyzed[0][0]
            # analyzed = [
            #     #[0][0]의 내용
            #     (
            #         [ 
            #             KiwiToken(form='안녕', tag='NNG', start=0, length=2, score=0.0, lemma='안녕'),
            #             KiwiToken(form='리라', tag='NNP', start=3, length=2, score=0.0, lemma='리라'),
            #         ],
            #         #[0][1]의 내용
            #         -123.456
            #     )
            # ]
            # ------------------------------------
            # analyzed[0][0]: 1번째 후보의 형태소 리스트
	        # analyzed[0][1]: 1번째 후보의 점수
            # ------------------------------------
	        # analyzed[1][0]: 2번째 후보의 형태소 리스트
	        # analyzed[1][1]: 2번째 후보의 점수
            # ------------------------------------
            # ...반복 -> 일단은 kiwi.analyze(text, top_n=1)에서 속성값top_n=1으로 설정, 1번째 후보 내용만 사용

            if DEBUG_KEYWORD:
                # 형태소 분석 결과의 길이를 출력
                try:
                    print(f"[keyword] 형태소: {len(morphemes)}")
                # 형태소 분석 결과가 없을 때 예외 처리
                except Exception:
                    print("[keyword] 형태소: 0 (형태소를 찾지 못했습니다.)")
                    pass
            
            # 형태소 분석 결과를 for문으로 순회하며 분석한다.
            # 처리방식:
            # 1차(표면형) 후보: 동사/형용사는 문장에 나온 그대로(예: “막혀서”, “좋아하는”)를 우선 토큰으로 둬. 문맥 신호(어미/활용)가 검색에 도움 될 때가 많다.
		    # 2차(표제어) 백업 후보: 그런데 표면형만 쓰면 너무 쪼개지거나 일반화가 안 돼서 놓칠 수 있다(예: “좋아하는” -> “좋아”). 그래서 같은 토큰을 표제어(lemma) 기반으로 한 버전을 보조 후보로 함께 담아둔다.
            # -> 예시: "좋아하는" -> 표면형("좋아하는"), 표제어("좋아")
            # -> 예시: "막혀서" -> 표면형("막혀서"), 표제어("막히다") -> "막히다"는 표제어가 없으므로 표면형 그대로 사용
            
		    # 3차(랭킹) : 이렇게 쌓인 (표면형/표제어) 후보들을 길이 품사 맥락 점수로 스코어링해서 가장 좋은 한 개를 뽑는다. 중복이나 덜 유의미한 토큰은 여기서 자연스럽게 밀려난다.

            for m in morphemes:
                # morphemes에 담겨 있는 form, tag, lemma 속성을 추출
                surface = m.form
                tag = m.tag
                # kiwi 구버전에서 lemma 추출 기능이 없을 수 있어 getattr함수 처리로 안전 접근 해준다.
                # 표제어(lemma)속성에 아무것도 없다면, surface를 사용
                lemma = getattr(m, "lemma", None) or surface 
                
                # 만약 morphes의 tag 속성이 _ALLOWED_TAGS에 포함되어 있다면...
                if tag in _ALLOWED_TAGS:
                    # 1차: 동사/형용사는 표면형(=예:문장 “막혀서 힘들다” 에서 surface="막혀서")를 우선 토큰화
                    tok = _normalize_token(surface, lemma, tag, text, m.start, prefer_surface_for_verbs=True)
                    # 만약 tok이 비어있지 않다면... candidates에 추가한다.
                    if tok:
                        # 자기지시/봇호명 토큰은 후보에서 제외
                        if tok in _SELF_REFERENTIAL_TOKENS:
                            continue
                        if DEBUG_KEYWORD:
                            print(f"[keyword] +cand(kiwi): {tok} [{tag}] (primary)")
                        candidates.append((tok, tag))
                        """
                        (1)입력: 
                        리라야 내가 좋아하는 커피는 아메리카노야
                        
                        (2)tok, tag 예시:
                        ("리라", "NNP")
                        ("좋아하는", "VV")
                        ("커피", "NNG")
                        ("아메리카노", "NNP")
                        """
                    # 2차: 동사/형용사 계열(VV/VA/VX/VCN)이면 표제어 기반 후보도 하나 더 만들어 보조로 넣는다.
                    if tag.startswith("V"):
                        # prefer_surface_for_verbs=False 로 호출 -> 표제어 규칙(…하다/…다 어간 정리)로 토큰화
                        lemma_tok = _normalize_token(
                            surface, # 원문에 보인 형태(예: "좋아하는")
                            lemma, # 표제어(예: "좋아하다")
                            tag, # 품사 태그
                            text, # 원문 전체 문장
                            m.start, # 이 형태소가 시작되는 인덱스
                            prefer_surface_for_verbs=False # 표면형 대신 표제어 기반으로 정규화
                        )
                        # 만약 lemma_tok이 비어있지 않다면... candidates에 추가한다.
                        if lemma_tok and lemma_tok != tok:
                            if lemma_tok in _SELF_REFERENTIAL_TOKENS:
                                pass
                            else:
                                if DEBUG_KEYWORD:
                                    # 디버그 모드에서 어떤 표제어 후보가 추가되는지 출력
                                    print(f"[keyword] +후보(kiwi): {lemma_tok} [{tag}] (표제어-백업)")
                                # 표제어 후보를 추가
                                candidates.append((lemma_tok, tag))

        # 만약 candidates가 비어있다면...
        # ---- 후보가 비었으면 간단 규칙 기반 백업 ----
        if not candidates:
            # 원문에서 한글/영문/숫자만 추출한 뒤 소문자화
            # 예) "안녕, Lira!! ㅎㅎ" -> ["안녕", "lira"]
            rough_tokens = [t.lower() for t in _KOREAN_KEEP.findall(text)]
            rough_tokens = [t for t in rough_tokens if len(t) > 1 and t not in _STOPWORDS and t not in _SELF_REFERENTIAL_TOKENS]

            if DEBUG_KEYWORD:
                print(f"[keyword] 폴백 토큰 후보: {rough_tokens}")

            # 후보가 남아 있으면 '가장 긴' 토큰을 선택 (의미어일 확률이 높음)
            # 추가 정보량이 많은 경향이 있어 대체 전략으로 유용
            if rough_tokens:
                if DEBUG_KEYWORD:
                    print("[keyword] 폴백: 가장 긴 토큰 사용")
                # 가장 긴 토큰을 선택
                fallback_tok = max(rough_tokens, key=len)
                # FB(=fallback) 태그로 표시해서 후속 랭킹에서 출처를 구분
                candidates.append((fallback_tok, "FB"))
        # 3차: 후보 랭킹 후 최종 top_n개 선택 (문맥/점수/빈도 기반)
        ranked_tokens = _rank_tokens(candidates, text)
        # 한 글자 분절 보정: 문장에 "이름"이 명시되었는데 선택 리스트에 "이" 또는 "름"이 있으면 "이름"으로 교체
        if "이름" in text and ranked_tokens:
            for i, tok in enumerate(ranked_tokens):
                if tok in {"이", "름"}:
                    ranked_tokens[i] = "이름"
        # 필터링: 자기지시/봇 호명, 불용어, 한 글자, 중복 제거(순서 보존)
        filtered = []
        seen = set()
        for tok in ranked_tokens:
            if not tok or tok in _SELF_REFERENTIAL_TOKENS or tok in _STOPWORDS or len(tok) < 2:
                continue
            if tok in seen:
                continue
            seen.add(tok)
            filtered.append(tok)
        # 결과 반환: top_n==1이면 str, else List[str]
        if not filtered:
            sel = "" if top_n == 1 else []
        else:
            if top_n == 1:
                sel = filtered[0]
            else:
                sel = filtered[:top_n]
        if DEBUG_KEYWORD:
            try:
                dbg = [f"{t}/{tag}" for t, tag in candidates]
                print(f"[keyword] 후보(품사 포함): {dbg} -> 선택: {sel}")
            except Exception:
                pass
        return sel

    except Exception as e:
        # 키워드 추출 전 과정에서 예외 발생 시, 디버그 모드일 때만 원인 출력
        if DEBUG_KEYWORD:
            print(f"[keyword] 추출 실패: {e} | 입력={text}")
        # 오류 시 빈 문자열 반환
        return "" if top_n == 1 else []