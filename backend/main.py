# backend/main.py
# role: App Entry Point
# content: FastAPI가 실행될때, 요청을 받아들이고 -> 처리를 시작하는 파일.

# 환경변수 사전호출(.env)
from dotenv import load_dotenv
load_dotenv()
# FastAPI에서 CORS(Cross Origin Resource Sharing) 처리를 위한 미들웨어를 불러온다.
# 목적: 프론트엔드(예: React, localhost:3000)와 백엔드(FastAPI, localhost:8000)가
#      서로 다른 도메인/포트에 있을 때, 브라우저 보안 정책에 의해 API 요청이 차단되지 않도록 허용하기 위함. 
# -> 포트 출처가 다르기 때문에 보안상 막히는 것을 허용해주기 위함임.
# -> 이 코드로 허용 중임 : app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
from fastapi.middleware.cors import CORSMiddleware

# FastAPI 앱 생성
from fastapi import FastAPI

# 라우터 정의를 갖고 있는 파일을 임포팅
from backend.api.routes import router

# 앱 인스턴스 생성
app = FastAPI(title="Lira")

# 운영 단계에서는 보안을 위해 특정 도메인/메서드만 허용하는 것이 권장됨  
# 현재는 포트폴리오/개발 용도로 모든 도메인과 메서드를 "*"로 열어두었음
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# - allow_origins=["*"]  : 모든 도메인 허용 (개발 단계용) 
                            # -> 실제 서비스 단계에서는 특정 도메인만 작성 : "https://주소.com"
# - allow_methods=["*"]  : 모든 HTTP 메서드 허용
                            # -> 실제 서비스 단계에서는 필요한 메서드만 작성
                            #   POST: 생성 (주로 많이 씀, 특히 로그인/데이터 전송 시) [C]
                            #   GET: 조회 [R]
                            #   PUT / PATCH: 수정 [U]
                            #   DELETE: 삭제 [D]
# - allow_headers=["*"]  : 모든 요청 헤더 허용
                            # -> 실제 서비스 단계에서는 필요한 헤더만 작성
                            #   "Content-Type" : JSON, multipart 등 요청 본문 형식 명시
                            #   "Authorization" : 토큰/세션 기반 인증에 필요

# 라우터 등록 -> api/routes.py에서 정의된 앤드포인트들을 앱에 연결
app.include_router(router, prefix="/api/lira")

# 루트 엔드포인트 -> 기본 서버 상태 확인용
@app.get("/")
def root():
    return {"message": "FASTAPI 서버가 작동중 입니다!"}