# emotion_engine.py
# role: 감정분류 모델 로드(goemotions 기반)
# content: front에서 감정분류 요청이 들어오면, 해당 요청을 처리하는 파일

# 뇌 영역
# role: 편도체 (Amygdala) 감정 기반 분류
# content: 외부 입력(문장)을 받아 감정적으로 처리하고 해석하는 1차 감정 처리 허브

# 1.transformers에서 pipeline을 임포트
from transformers import pipeline
# 1-1. 영어를 제외한 언어 번역을 위한 함수 임포트
from backend.utils.translation import translate_to_english
# 2.SamLowe/roberta-base-go_emotions 모델(sigmoid)을 로드
emotion_classifier = pipeline(
    "text-classification",
    model="SamLowe/roberta-base-go_emotions",
    
    # sigmoid로 분석한 모든 감정 점수를 반환 하도록 설정
    top_k=None
)

# 3.감정 분석 처리함수
# 사용자 입력 텍스트를 받아 감정 점수 분류
# - 참고: GoEmotions는 멀티라벨 시그모이드라 각 감정 점수는 독립적(합이 1 아님)

# 패러미터 & 리턴 값 설명
# - text: 분석 대상 문장 -> routes.py에서 request.text로 전달받음
# - threshold: 감정의 최소 강도 점수 (0.3 이상만 유의미하다고 판단).
# - sigmoid기반 감정분류이기에 0.3미만은 무의미한 노이즈 감정으로 간주 판단하기 때문.
# - 반환: [{"label": 감정명, "score": 강도}] 형태의 리스트
def analyze_emotion(text: str, threshold: float = 0.3) -> list[dict]:
    
    # 예외처리를 통해 모델오류, 입력오류를 사전 방지
    try:
        # 패러미터로 받은 텍스트(한국어 -> 영어)를 상기 모델(SamLowe/roberta-base-go_emotions)에 전달하여 결과 추출
        # -> goemotions 모델은 영어로 학습되어 있으므로, 한국어 입력을 영어로 번역 후 분석
        translated = translate_to_english(text)        

        # 감정 점수 기준 필터링 후 Top-3 추출(단일감정 아님)
        # - 기준: GoEmotions 모델의 감정 점수
        # - 출처: https://arxiv.org/abs/2005.00547
        # - top-3 추출근거 : Cognitive Load Theory, Cowan (2001):처리 항목이 3~4개를 넘으면 공감 대화 품질 저하
        # sigmoid임으로 점수 값이 0~1 사이의 실수로 반환됨. 단, 두 감정값 총합이 1이 아님, 각 감정값 범주: 0~1
        # emotion_classifier(translated)는 List[List[Dict]] 형태로 반환된다.
        # 사용자 입력은 복수문장이 아니기에 -> List[0]으로 분석내용을 받아준다.
        result = emotion_classifier(translated)[0]
        # result 변수에 담기는 값 예시: list[dict] 
        # [
        #     {'label': 'joy', 'score': 0.872},
        #     {'label': 'sadness', 'score': 0.203},
        #     {'label': 'anger', 'score': 0.024},
        #     ...
        # ]

        # 유의미한 감정만 필터링 (threshold 이상)
        # 감정 점수로 필터링된 값 result에서 r변수로 추출
        # 만약 r의 score값이 0.3 이상이면, filtered변수에 추가
        # 상기에서 api로 감정라벨링과 감정값을 추출한 뒤에, 필터링까지 진행한다.
        # 최종적으로, 유의미한 감정 라벨과 점수만 포함된 리스트를 반환
        # 예시: [{"label": "joy", "score": 0.78}, {"label": "sadness", "score": 0.35}]
        # 전부 0.3 이상이다.
        filtered_all = []
        for r in result:
            if r["score"] >= threshold:
                filtered_all.append({
                    "label": r["label"], 
                    "score": round(r["score"], 3)
                })
        # 이 filtered 결과는 routes.py 내 /generate 엔드포인트에서 analyze_emotion(request.text) 호출 결과(리턴될 내용)로 사용되며,
        # 이후 FastAPI 응답(JSON)으로 클라이언트에 전달된다.
        filtered = sorted(filtered_all, key=lambda x: x["score"], reverse=True)[:3]

        # 핵심: threshold 이상 감정이 없으면 가장 높은 감정 1개만 기본으로 포함
        if not filtered:
            # threshold를 넘는 감정이 없을 경우, 가장 높은 감정 하나만 기본값으로 사용
            top_r = sorted(result, key=lambda x: x["score"], reverse=True)[0]
            # filtered에 가장 높은 감정 하나만 추가
            filtered = [{"label": top_r["label"], "score": round(top_r["score"], 3)}]

        return filtered
    
    
    
    # 감정 분석 중 오류 발생 시, 후속처리
    except Exception as e:

        # 오류 메시지 출력
        print(f"[LI-EMO][감정 분석 모듈] [emotion_engine.py->analyze_emotion()]감정 분석 실패: {e}")
        print("[LI-EMO][감정 분석 모듈] 관련 뇌 영역: 편도체 (Amygdala) 에러")
        print("[LI-EMO][감정 분석 모듈] 역할: 외부 입력을 감정적으로 해석하는 1차 감정 처리 허브 에러")

        # 빈 리스트로 반환
        return []