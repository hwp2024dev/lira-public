# reset_memory.py
# 역할: 개발 및 테스트를 위해 MongoDB와 Weaviate의 기억 데이터를 초기화합니다.
# 사용 예:
# python3 backend/utils/reset_memory.py -y

# import modules
from pymongo import MongoClient
import weaviate
import os
import sys
import time
import argparse # 해당 스크립트를 실행시킬때 인자를 반영하기 위한 모듈
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드한다.
load_dotenv()

# -------------------- 연결 헬퍼 --------------------
def _mongo_ping(client) -> bool:
    """MongoDB 연결 확인: ping 커맨드로 빠르게 확인."""
    # 1) admin DB에 'ping' 명령을 보내서 연결 상태를 테스트한다.
    #    - 성공하면 예외가 발생하지 않고 True를 반환한다.
    try:
        client.admin.command("ping")  # 연결 OK면 {'ok': 1} 형태의 응답
        return True
    except Exception as e:
        # 2) 연결이 안 되면 에러 메시지를 출력하고 False를 반환한다.
        print(f"[MongoDB] 연결 확인 실패: {e}")
        return False

def _wait_weaviate_ready(client, timeout: int = 30) -> bool:
    """Weaviate가 준비될 때까지 schema.get()을 폴링."""
    # 1) 시작 시간을 저장. (경과 시간을 계산하기 위해)
    start = time.time()
    # 2) timeout(초) 동안 1초 간격으로 준비 상태를 확인
    while time.time() - start < timeout:
        try:
            # 3) schema.get()이 성공하면 서버준비 완료
            client.schema.get()
            return True
        except Exception:
            # 4) 아직 준비 전이면 1초 대기 후 재시도
            time.sleep(1)
    # 5) 위 반복이 끝났다는 건 시간 초과이므로 경고를 출력하고 False를 반환한다
    print("[Weaviate] 준비 신호 대기 시간 초과(ready 대기 실패)")
    return False

# -------------------- 유틸리티 함수 --------------------
def confirm_or_stop(message: str, yes: bool):
    """
    데이터 삭제를 실행하기 전에 사용자에게 확인을 받는 함수.
    -y 옵션이 주어지면 확인 절차를 건너뛴다.
    """
    # 인자가 -y/--yes가 지정된 경우
    if yes:
        # 확인절차 없이 바로 진행                              
        return
    # 사용자에게 확인 프롬프트 출력
    ans = input(                         
        f"{message} 계속하시려면 'DROP'을 입력하세요: "
    ).strip()
    # 사용자가 'DROP'을 입력하지 않았다면
    if ans != "DROP":
        # 안내 메시지 출력                    
        print("중단합니다.")
        # 비정상 종료 코드로 즉시 종료              
        sys.exit(1)                      

# -------------------- MongoDB 초기화 --------------------
def reset_mongo(mongo_url: str, db_name: str, collection: str, drop_db: bool):
    """MongoDB 컬렉션의 모든 문서를 삭제하거나, 데이터베이스 자체를 삭제합니다."""
    # MongoDB 접속 클라이언트 생성
    client = MongoClient(mongo_url)
    if not _mongo_ping(client):
        print("[MongoDB] 연결 불가: URL/포트 설정을 확인하세요 (도커 기본: mongodb://localhost:27017/).")
        client.close()
        return
    # 대상 DB 핸들      
    db = client[db_name]
    # 대상 컬렉션 핸들
    coll = db[collection]                
    # 타깃 표시
    print(f"[MongoDB] 대상: {mongo_url} db={db_name} coll={collection}") 
    try:
        # 삭제전 문서 수 추산
        before_cnt = coll.estimated_document_count()  
    except Exception:
        # 없을 시 0으로 폴백
        before_cnt = 0
    # 삭제전 문서 수 출력                   
    print(f"[MongoDB] 삭제전 문서 수: {before_cnt}")   

    # DB 전체를 삭제할지 여부
    if drop_db:
        # 데이터베이스 삭제
        client.drop_database(db_name)
        # 삭제된 DB명 출력
        print(f"[MongoDB] 데이터베이스 '{db_name}' 삭제 완료")
    else:
        # 컬렉션 내 모든 문서 삭제
        res = coll.delete_many({})
        # 삭제된 문서 수 출력
        print(f"[MongoDB] 삭제된 문서 수: {res.deleted_count}")
        try:
            # 삭제후 문서 수 추정
            after_cnt = coll.estimated_document_count()
            # 사후 카운트 출력
            print(f"[MongoDB] 삭제후 문서 수: {after_cnt}")
        except Exception:
            # 카운트 실패시 pass로 넘긴다.
            pass                         
    # 연결된 클라이언트 닫기        
    client.close()                      

# -------------------- Weaviate 초기화 --------------------
def delete_all_weaviate_objects(client, class_name: str, batch_size: int = 200) -> int:
    """
    Weaviate 클래스 내의 모든 객체를 삭제한다.
    - limit(batch_size)로 끊어 가져와 비는 순간까지 반복 삭제한다.
    """
    # 누적 삭제 건수를 저장할 변수 초기화
    total_deleted = 0
    # 객체가 더 이상 없을 때까지 반복                                  
    while True:                                        
        try:
            # 클래스 내 객체들을 조회
            res = client.data_object.get(
                # 어떤 클래스에서 가져올지 지정              
                class_name=class_name,
                # 한 번에 얼마나 가져올지 크기 제한
                limit=batch_size
            )
            # res값 예시
            # {
            #     "objects": [
            #         {
            #         "id": "1234-5678-...", --> uuid
            #         "class": "SemanticArchive",
            #         "properties": {
            #             "text": "오늘 날씨가 좋다",
            #             "label": "neutral"
            #         },
            #         [{...}]
            #     ]
            # }

            # 응답에서 객체 리스트 추출(없으면 빈 리스트)
            objects = res.get("objects", [])
            # 가져온 객체가 없다면          
            if not objects:
                # 루프종료                            
                break
            # 조회된 각 객체에 대해                                  
            for obj in objects:
                # 객체의 UUID 추출 --> weaviate의 object의 고유 id --> 자세한 내용은 상기의 res값 예시를 보면 됨.
                uuid = obj.get("id")
                # UUID가 존재한다면,
                if uuid:
                    # 해당 객체 삭제 요청                               
                    client.data_object.delete(         
                        uuid=uuid,
                        class_name=class_name
                    )
                    # 누적 삭제 수 카운트 증가
                    total_deleted += 1
        # 조회/삭제 과정에서 예외 발생 시
        except Exception as e:
            # 오류 로그 출력                         
            print(f"[Weaviate] 객체 삭제 중 오류 발생: {e}")
            # 더 진행하지 않고 종료  
            break
         # 서버 부하 완화를 위한 짧은 대기                                      
        time.sleep(0.1)
    # 총 삭제된 객체 수 반환
    return total_deleted                               


def reset_weaviate(weaviate_url: str, class_name: str, drop_schema: bool):
    """Weaviate 클래스의 모든 객체를 삭제하거나, 선택적으로 클래스 스키마 자체를 삭제한다."""

    # Weaviate 클라이언트 인스턴스 생성
    client = weaviate.Client(weaviate_url)
    _wait_weaviate_ready(client, timeout=30)
    # 대상 엔드포인트/클래스 출력             
    print(f"[Weaviate] 대상: {weaviate_url} 클래스={class_name}") 

    try:
        # 현재 Weaviate 스키마 조회
        schema = client.schema.get()
        # 등록된 클래스 이름 목록 생성                   
        existing_classes = []
        # 스키마 안의 클래스 목록 순회
        for c in schema.get("classes", []):
            schema_class = c.get("class")
            existing_classes.append(schema_class)

    # 스키마 조회 실패 시
    except Exception as e:
        print(f"[Weaviate] 스키마를 가져오는 데 실패했습니다: {e}")
        # 이후 작업 중단
        return 
                                            
    # 정확(Exact) 매칭으로 클래스 존재 여부 확인
    if class_name not in existing_classes:          
        print(f"[Weaviate] Class '{class_name}'를 찾을 수 없습니다.")  
        print(f"[Weaviate] 사용 가능한 클래스: {existing_classes}")
        # 없을시, 작업중단
        return

    try:
        # weaviate의 client 객체의 aggregate 메서드 호출하여 삭제전 저장된 내용의 개수를 확인한다.
        agg = client.query.aggregate(class_name)
        # agg에 집계된 내용을 with_meta_count().do() 함수로 meta 안에 있는 count를 가져와 개수를 확인한다.       
        agg = agg.with_meta_count().do()
        # agg = {
        #         "data": {
        #             "Aggregate": {
        #             "SemanticArchive": [
        #                 {
        #                 "meta": {
        #                     "count": 120   # <-- 이게 클래스 안에 있는 객체 총 개수
        #                 }
        #                 }
        #             ]
        #             }
        #         }
        #        }

        # 총 개수 추출              
        before_count = agg["data"]["Aggregate"][class_name][0]["meta"]["count"]
        # 삭제전 개수 출력
        print(f"[Weaviate] 삭제전 객체 수: {before_count}")
    except Exception:
        # 카운트 확인 실패 시 로그
        print("[Weaviate] 삭제전 객체 수를 확인하지 못했습니다.")
    # 객체 일괄 삭제 실행
    deleted_count = delete_all_weaviate_objects(       
        client=client,
        class_name=class_name
    )
    # 삭제 결과 출력
    print(f"[Weaviate] 삭제된 객체 수: {deleted_count} (클래스: {class_name})")
    # 스키마(클래스 정의)까지 삭제할지 여부
    if drop_schema:                                    
        try:
            # 클래스 스키마 삭제 요청
            client.schema.delete_class(class_name)
            # 스키마 삭제 완료 로그
            print(f"[Weaviate] 클래스 '{class_name}' 삭제 완료")
        # 스키마 삭제 실패시
        except Exception as e:
            # 오류 로그 출력                         
            print(f"[Weaviate] 클래스 삭제 실패: {e}")         
# -------------------- 메인 실행 함수 --------------------
def main():
    # CLI 인자 파서 생성
    parser = argparse.ArgumentParser(                  
        description="LIRA 메모리 리셋 스크립트 (MongoDB/Weaviate). 기본 도커 localhost 설정을 사용합니다.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Mongo 관련 인자들: 환경변수 기본값 사용
    parser.add_argument("--mongo-url", default=os.getenv("MONGO_URL", "mongodb://localhost:27017/"))
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB_NAME", "lira_memory"))
    parser.add_argument("--mongo-collection", default=os.getenv("MONGO_COLLECTION", "memory"))

    # Weaviate 관련 인자들: 환경변수 기본값 사용
    parser.add_argument("--weaviate-url", default=os.getenv("WEAVIATE_URL", "http://localhost:8080"))
    parser.add_argument("--weaviate-class", default=os.getenv("WEAVIATE_CLASS", "SemanticArchive"))

    # 삭제 옵션
    parser.add_argument("--drop-db", action="store_true",
                        help="MongoDB 데이터베이스 자체를 삭제합니다 (강력).")
    parser.add_argument("--drop-schema", action="store_true",
                        help="Weaviate 클래스를 삭제합니다 (강력).")

    # 확인 생략 옵션 (-y / --yes)
    parser.add_argument("-y", "--yes", action="store_true",
                        help="확인 프롬프트 없이 바로 진행합니다.")

    args = parser.parse_args()

    # 실행 전 안내 메시지
    print("=" * 60)
    print("*** 연결 정보(기본값) ***")
    print(f" - MONGO_URL: {os.getenv('MONGO_URL', 'mongodb://localhost:27017/')}")
    print(f" - WEAVIATE_URL: {os.getenv('WEAVIATE_URL', 'http://localhost:8080')}")
    print("=" * 60)
    print("*** 삭제 전 용어 안내 ***")
    print(" - MongoDB의 '문서(Document)' = 하나의 데이터(JSON 객체 단위) -> 상위개념: '컬렉션(Collection)'")
    print(" - Weaviate의 '객체(Object)' = 하나의 데이터 인스턴스(uuid로 구분) -> 상위개념: '클래스(Class)'")
    print("즉, '문서 수'나 '객체 수'는 모두 DB 안에 저장된 데이터 건수를 뜻한다.")
    print("=" * 60)

    # 위험 작업 실행 전 확인
    if args.drop_db:
        confirm_or_stop(f"[경고] MongoDB 데이터베이스 '{args.mongo_db}'를 삭제합니다.", args.yes)
    if args.drop_schema:
        confirm_or_stop(f"[경고] Weaviate 클래스 '{args.weaviate_class}'를 삭제합니다.", args.yes)

    # 실제 초기화 실행
    reset_mongo(args.mongo_url, args.mongo_db, args.mongo_collection, drop_db=args.drop_db)
    print("-" * 20)
    reset_weaviate(args.weaviate_url, args.weaviate_class, drop_schema=args.drop_schema)

# 파일 직접 실행할때 main()을 우선 실행한다.
if __name__ == "__main__":
    main()