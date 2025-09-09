// liraResponse.ts
// 역할: Lira 응답 처리 모듈

// 백엔드 에서의 응답의 내용을 정의힌다.
export type LiraResponse = {
    output: string;
    emotion?: {
        emotion_1st_label: string;
        emotion_1st_score: number;
        emotion_2nd_label?: string;
        emotion_2nd_score?: number;
        emotion_3rd_label?: string;
        emotion_3rd_score?: number;
        emotion_mode?: string;
    };
};

// 백엔드 FastAPI와 통신
// 역할은 아래와 같다.
// 1. 사용자 입력 -> 백엔드에 전달
// 2. 백엔드 처리 -> 사용자에게 반환
// 3. 반환데이터는 처리하는데 시간이 걸리므로 async 함수로 정의하여 응답이 오면 리턴해준다.
// 4. 리턴값은 Promise<LiraResponse> 형태로 줄 것을 약속한다. -> LiraResponse 이외 규격은 반환금지 약속!!
export async function sendMessageToLira(userId: string, sessionId: string, text: string): Promise<LiraResponse> {

    // 비동기 요청을 보내고, 응답이 올때까지 기다린다. -> async 함수 정의 -> await 키워드를 사용한다.
    // 응답으로 받는 내용은 아래와 같다.
    const res = await fetch("/api/lira/generate", {
        // HTTP 요청의 메서드는 POST로 설정한다.
        // POST 메서드는 서버에 데이터를 전송할 때 사용된다.(보안목적으로 GET이 아닌 POST를 사용한다.)
        method: "POST",
        // 요청의 body에 사용자 ID, 세션 ID, 텍스트를 JSON 형태로 담아 보낸다.
        headers: { "Content-Type": "application/json" },
        credentials: "include", // 세션 쿠키 및 인증정보를 포함하여 요청 (세션 유지 목적)
        // 이때 JSON.stringify를 사용하여 객체를 json데이터 형태의 문자열로 변환해 준다.
        body: JSON.stringify({
            user_id: userId,
            session_id: sessionId,
            text: text
        })
    });
    // 응답이 성공적이지 않으면 에러를 발생시킨다. (상태코드 + 상태텍스트 함께 표시하여 디버깅)
    if (!res.ok) {
        throw new Error(`Lira 응답 오류: ${res.status} ${res.statusText}`);
    }
    // 응답을 JSON 형태로 파싱하여 LiraResponse 타입으로 반환한다.
    return await res.json();
}