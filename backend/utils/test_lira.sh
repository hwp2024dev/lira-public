#!/usr/bin/env bash

# 에러 발생 시 즉시 중단
set -euo pipefail
# 안전한 구분자 설정
IFS=$'\n\t'
# 기본 API 주소 설정
: "${BASE:=http://localhost:8000}"

# ----------------------------------------
# 테스트 내용 요약
# 각 테스트 별 유저와 세션이 다릅니다.

# ===  테스트 내용 ===
# 1~3: 이름 저장, 불러오기 확인 (userA, sessionA1) / (userB, sessionB1)
# 4~5: 감정 문장 저장, 불러오기 확인 (userA, sessionA2)
# 6~7: 일정 정보 저장, 불러오기 확인 (userA, sessionA4)
# 8~9: 임시 메모 저장, 불러오기 확인 (userA, ttlTest)
# 10: TTL 기능을 확인하기 위한 유효시간 변경(24h -> 10초)
# 11: TTL 만료 대기 및 확인 (session: ttlTest)
# 12: 장기 기억 초기화(DB 삭제) (전체 세션 대상)
# 13: TTL 만료 후 임시 메모 회상 실패 확인 (userA, ttlTest)
#   * TTL를 통한 초기화를 했기 때문에 회상에 실패해야함
# 14: 환각 방지 테스트(근거 없는 질문 시 안전 응답) (userC, sessionC1)

# ----------------------------------------
echo "=== LIRA 기능 통합 테스트 시작 ==="
echo "API 주소: $BASE"
echo

# 1) UserA 이름 저장
echo "=== 1) UserA 이름 저장 테스트 ==="
echo "검증: 이름 저장 기능 확인"
echo "대상: user_id=userA, session_id=sessionA1"
echo "입력: '안녕하세요, 제 이름은 A입니다.'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"sessionA1","text":"안녕하세요, 제 이름은 A입니다."}'
echo;echo
sleep 5

# 2) UserB 이름 저장
echo "=== 2) UserB 이름 저장 테스트 ==="
echo "검증: 이름 저장 기능 확인"
echo "대상: user_id=userB, session_id=sessionB1"
echo "입력: '안녕하세요, 제 이름은 B입니다.'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userB","session_id":"sessionB1","text":"안녕하세요, 제 이름은 B입니다."}'
echo;echo
sleep 5

# 3) UserB 이름 불러오기
echo "=== 3) UserB 이름 불러오기 테스트 (B만 나와야 함) ==="
echo "검증: 저장한 이름 정확히 불러오기"
echo "대상: user_id=userB, session_id=sessionB1"
echo "입력: '제 이름이 뭐였죠?'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userB","session_id":"sessionB1","text":"제 이름이 뭐였죠?"}'
echo;echo
sleep 5

# 4) UserA 감정 문장 저장
echo "=== 4) UserA 감정 문장 저장 테스트 ==="
echo "검증: 감정 문장 저장 (특별한 문장 기억)"
echo "대상: user_id=userA, session_id=sessionA2"
echo "입력: '오늘 정말 너무 기뻤어. 드디어 오늘 나만의 RAG시스템이 완성됐어!!'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"sessionA2","text":"오늘 정말 너무 기뻤어. 드디어 오늘 나만의 RAG시스템이 완성됐어!!"}'
echo;echo
sleep 5

# 5) UserA 감정 문장 불러오기
echo "=== 5) UserA 감정 문장 불러오기 테스트 ==="
echo "검증: 감정 문장 정확히 기억하는지 확인"
echo "대상: user_id=userA, session_id=sessionA2"
echo "입력: '내가 기쁜 이유가 뭐였지?'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"sessionA2","text":"내가 기쁜 이유가 뭐였지?"}'
echo;echo
sleep 5

# 6) 일정 정보 저장
echo "=== 6) 일정 정보 저장 테스트 ==="
echo "검증: 날짜와 장소 정보 저장"
echo "대상: user_id=userA, session_id=sessionA4"
echo "입력: '내일 오후 3시 강남에서 민수랑 미팅 있어. 기억해줘.'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"sessionA4","text":"내일 오후 3시 강남에서 민수랑 미팅 있어. 기억해줘."}'
echo;echo
sleep 5

# 7) 일정 정보 불러오기
echo "=== 7) 일정 정보 불러오기 테스트 ==="
echo "검증: 저장한 일정 정확하게 불러오기"
echo "대상: user_id=userA, session_id=sessionA4"
echo "입력: '내 일정(날짜/장소) 뭐였지?'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"sessionA4","text":"내 일정(날짜/장소) 뭐였지?"}'
echo;echo
sleep 5

# 8) 임시 메모 저장 (TTL 적용)
echo "=== 8) 임시 메모 저장 테스트 (24시간 만료) ==="
echo "검증: 임시 메모가 STM에 저장되는지 확인"
echo "대상: user_id=userA, session_id=ttlTest"
echo "입력: '임시 메모 : 나는 커피를 좋아한다'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"ttlTest","text":"임시 메모 : 나는 커피를 좋아한다"}'
echo;echo
sleep 5

# 9) 임시 메모 즉시 불러오기
echo "=== 9) 임시 메모 즉시 불러오기 테스트 ==="
echo "검증: 저장한 임시 메모가 바로 불러와지는지 확인"
echo "대상: user_id=userA, session_id=ttlTest"
echo "입력: '아까 임시 메모 뭐였지?'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"ttlTest","text":"아까 임시 메모 뭐였지?"}'
echo;echo
sleep 5

# 10) 임시 메모 TTL 만료 시간 단축 (10초)
echo "=== 10) 임시 메모 TTL 단축 (24시간 -> 10초) 테스트 ==="
echo "설명: Redis에서 임시 메모 만료시간을 10초로 변경"
echo "반환값: 1은 성공, 0은 실패"
echo "대상 Redis 키: session:ttlTest"
docker exec redis redis-cli expire session:ttlTest 10
echo
sleep 5

# 11) TTL 만료 대기 및 확인
echo "=== 11) TTL 만료 대기 및 확인 ==="
echo "설명: TTL 값이 -2가 되면 키가 삭제된 것임"
echo "대상 Redis 키: session:ttlTest"
while true; do
  TTL_VAL=$(docker exec redis redis-cli --raw ttl session:ttlTest 2>/dev/null | tr -d '\r')
  echo "현재 TTL: $TTL_VAL"
  if [ "$TTL_VAL" -eq -2 ]; then
    echo "-> 임시 메모 만료 완료 및 삭제됨"
    break
  fi
  sleep 1
done
echo

# 12) 장기 기억 초기화 (MongoDB, Weaviate 데이터 삭제)
echo "=== 12) 장기 기억 초기화 테스트 ==="
echo "설명: 모든 장기 기억 데이터 삭제"
python3 "$(dirname "$0")/reset_memory.py" -y
echo "장기 기억 초기화 완료"
echo
sleep 5

# 13) TTL 만료 후 임시 메모 불러오기 시도
echo "=== 13) TTL 만료 후 임시 메모 불러오기 테스트 ==="
echo "검증: 임시 메모가 사라져서 불러오기 실패해야 함"
echo "대상: user_id=userA, session_id=ttlTest"
echo "입력: '아까 임시 메모 뭐였지?'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userA","session_id":"ttlTest","text":"아까 임시 메모 뭐였지?"}'
echo;echo
sleep 5

# 14) 환각 방지 테스트 (근거 없을 때 안전 응답)
echo "=== 14) 환각 방지 테스트 ==="
echo "검증: 근거 없는 질문에 추측 대신 안전 응답(모르겠어요/기억에 없어요)인지 확인"
echo "대상: user_id=userC, session_id=sessionC1"
echo "입력: '내 혈액형 기억하니?'"
curl -s -X POST "$BASE/api/lira/generate" -H "Content-Type: application/json" \
  -d '{"user_id":"userC","session_id":"sessionC1","text":"내 혈액형 기억하니?"}'
echo;echo