# 번역 모듈: GPT API를 활용해 한글을 영어로 번역
import openai
import os

# 환경 변수에서 API 키 불러오기 (또는 별도 설정 가능)
# openai.api_key = os.getenv("UPSTAGE_API_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")

def translate_to_english(korean_text: str) -> str:
    """
    llm을 이용해 한글 텍스트를 영어로 번역
    """
    try:
        response = openai.ChatCompletion.create(
            # model="solar-pro2",
            model="gpt-4o",
            messages=[
                # GoEmotions로 분석하기 위해서는 영어로 번역 필요하기 때문에
                # -> content란에 "Respond with English only"로 작성한다.
                {
                    "role": "system",
                    "content": "Translate the following Korean text to natural English. Respond with English only."
                },
                {
                    "role": "user",
                    "content": korean_text
                }
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[ERROR] 번역 실패:", e)
         # 번역 실패 시 원문 반환
        return korean_text