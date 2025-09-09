# semantic_archive.py
# role: 의미기반 기억 저장소
# content: cohere 백터 기반 임베딩 + weaviate 저장 및 검색

# 임포트 정의
import os
from dotenv import load_dotenv
from cohere import Client as CohereClient
import json
import weaviate
from datetime import datetime, timezone

# 0. 환경변수 로드
# .env 파일에서 API 키와 Weaviate URL을 로드
load_dotenv()

# 1.cohere 클라이언트 호출
cohere_client = CohereClient(os.getenv("COHERE_API_KEY"))

# 1-1.사용자 입력을 cohere로 백터 임베딩(weaviate에 저장된 기억을 검색하기 위한 임베딩)
def embed_text(query: str) -> list[float]:
    # 실제 받는 타입 확인
    # print(type(query))
    # 혹시 모를 타입 문제 대비
    query = str(query).strip() 
    response = cohere_client.embed(
        texts= [query],
        # 임베딩 모델은 multilingual-v3.0 사용
        # 임베딩 크기는 1024차원임
        model="embed-multilingual-v3.0",
        input_type="search_query"
    )
    # 검색용 임베딩 백터를 리턴해준다.
    return response.embeddings[0]

# 2.weaviate 클라이언트 호출
weaviate_client = weaviate.Client(os.getenv("WEAVIATE_URL"))

# 2-1. weaviate에 저장할 클래스(=처리공간,틀) 정의
def init_weaviate_schema():
    class_obj = {
        "class": "SemanticArchive",
        # 벡터화는 cohere에서 처리하므로 none으로 설정
        "vectorizer": "none",  
        # 저장되는 기억의 최소형식
        "properties": [
            {"name": "user_id", "dataType": ["string"]},
            {"name": "text", "dataType": ["text"]},
            {"name": "label", "dataType": ["string"]},
            {"name": "score", "dataType": ["number"]},
            {"name": "emotions_json", "dataType": ["text"]},
            {"name": "timestamp", "dataType": ["date"]},
        ]
    }
    schema = weaviate_client.schema.get()
    existing = [cl.get("class") for cl in schema.get("classes", [])]
    if "SemanticArchive" not in existing:
        weaviate_client.schema.create_class(class_obj)

# 3. 의미기반 저장
def store_semantic_memory(user_id: str, text: str, emotions: list[dict]):
    # 저장 텍스트 임베딩 생성 (SemanticArchive 클래스에 저장)
    # 예 : 저장 단어의 좌표가 (10,5)면 // embed_text(text), 검색 좌표는 (8,3) //embed_text(query) 입력해서 검색하는거랑 같음
    vector = embed_text(text)
    # 가장 높은 감정을 추출
    top_emotion = max(emotions, key=lambda x: x["score"])
    # weaviate에 저장할 데이터 정의
    data_object = {
        "user_id": user_id,
        "text": text,
        "label": top_emotion["label"],
        "score": round(top_emotion["score"], 3),
        "emotions_json": json.dumps(emotions, ensure_ascii=False),
        # 현재 시간 UTC로 저장  
        "timestamp": datetime.now(timezone.utc).isoformat()  
    }
    # weaviate에 데이터 저장
    weaviate_client.data_object.create(
        data_object=data_object,
        class_name="SemanticArchive",
        vector=vector
    )
# 4.의미 기반 검색 (top_k = 3개 검색) -> cohere로 임베딩된 벡터를 사용하여 검색
    # 연합피질 (Association Cortex) 의미 연상 및 벡터 기반 유사성 계산
    # 참고논문 Cognitive Load Theory, Cowan (2001):처리 항목이 3~4개를 넘으면 공감 대화 품질 저하
def search_semantic_memory(query: str, top_k: int = 3, user_id: str | None = None): 
    # 검색 쿼리 임베딩 생성
    # 예 : 저장 단어의 좌표가 (10,5)면 // embed_text(text), 검색 좌표는 (8,3) //embed_text(query) 입력해서 검색하는거랑 같음
    query_vector = embed_text(query)

    # weaviate에서 유사한 객체 검색
    # weaviate python client 체이닝 방식으로 작성했기에 아래에 주석으로 설명하고자 함.

    # .with_near_vector : query_vector와 유사한 벡터를 가진 객체 검색
    # .with_limit : top_k = 3개만 검색 
    # .with_additional : 저장된 기억의 벡터와 질문 백터와의 유사도 점수 확인(weaviate의 내장함수 기능)
    # -> cosine similarity 기반으로 계산되며, 1.0에 가까울수록 의미적으로 매우 유사함
    # https://weaviate.io/developers/weaviate/api/graphql/search-operators/nearvector#with_additional
    # .do() : 실제 쿼리 실행
    # 기본 쿼리 구성
    query_builder = (
        weaviate_client.query
        .get("SemanticArchive", ["user_id", "text", "label", "score", "timestamp"])
        .with_near_vector({"vector": query_vector})
        .with_limit(top_k)
        .with_additional(["certainty"])
    )
    # user_id가 주어지면 동일 사용자 데이터만 사전 필터링
    if user_id:
        query_builder = query_builder.with_where({
            "path": ["user_id"],
            "operator": "Equal",
            "valueText": user_id
        })
    response = query_builder.do()
    
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
    # 상기 내용은 response.get("data", {}).get("Get", {}).get("SemanticArchive", [])에서 리턴해주는 값이다.
    return response.get("data", {}).get("Get", {}).get("SemanticArchive", [])

# 모듈 초기화 (최초 1회)
init_weaviate_schema()