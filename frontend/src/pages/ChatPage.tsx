// src/pages/ChatPage.tsx
// 역할: 채팅 페이지 컴포넌트로, 사용자 메시지를 입력하고 Lira의 응답을 표시하는 UI를 구성한다.

// import modules
import React, { useState, useEffect, useRef } from "react";
// 백엔드 api와 통신하여 Lira의 응답을 가져오는 함수
import { sendMessageToLira } from "../api/liraResponse";
// 사용자 상태를 관리하는 store에서 사용자 정보를 가져오는 훅
import { useUserStore } from "../store/userStore";
// 감정 상태를 관리하는 store에서 감정 정보를 가져오는 훅
import { useEmotionStore } from "../store/emotionStore";
// 감정 레이블 타입을 가져오기 위한 import
import { EmotionLabel } from "../store/emotionStore";
// EmotionCanvasWrapper 컴포넌트를 가져와서 감정 애니메이션을 렌더링한다.
import EmotionCanvasWrapper from "../components/EmotionCanvasWrapper";
// CSS 스타일을 가져온다.
import "./chatpage.css";

// ChatPage 컴포넌트 정의
const ChatPage: React.FC = () => {

  // 1. 사용자 입력(input창에 입력 중인 텍스트)을 저장하는 상태 변수
  // userMessage: 현재 입력창에 사용자가 입력하고 있는 텍스트 값
  // setUserMessage: 이 값을 변경하는 함수 (onChange에서 사용됨)
  // useState<string>(""): 초기값은 빈 문자열 (""), 타입은 문자열 (string)
  const [userMessage, setUserMessage] = useState<string>("");

  // 2. 대화 기록 전체를 저장하는 메시지 배열 상태
  // messages: 지금까지 오간 모든 채팅 메시지 목록
  // setMessages: 메시지를 추가하거나 초기화할 때 사용하는 함수
  // 빈 배열 ([]) -> 대화 시작 전 상태
  const [messages, setMessages] = useState<
    { role: "user" | "lira"; content: string }[]
  >([]);

  // 3. 메시지가 자동으로 추가될 때마다, 채팅창을 아래로 스크롤하기 위한 기능설정.

  // 3-1. HTMLDivElement를 참조할 수 있는 ref(참조 객체)를 생성한다.
  //      이 ref는 나중에 리엑트가 생성한 <div> 요소에 자동으로 연결될 예정이며,
  //      현재 초기값은 null이므로 아직 DOM 요소는 연결되지 않은 상태다.
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // 3-2. useEffect의 messages 배열이 변경될 때마다(트리거), 채팅창(chatContainerRef)의 스크롤 위치를 조정하여, 스크롤이 자동으로 아래로 내려간다.
  useEffect(() => {
    // 3-2-1. 먼저, chatContainerRef.current 내용을 가져온다.
    const chatContainer = chatContainerRef.current;
    // messages 배열에는 사용자와 Lira의 메시지가 담겨있으며,
    // chatContainerRef.current에는 채팅창의 <div> 요소가 담겨있다.

    // 담긴 내용 : 
    // <div className="chat-history" ref={chatContainerRef}>
    //  <div class="chat-bubble user">
    //    <strong>나</strong>: 안녕
    //  </div>
    //  <div class="chat-bubble lira">
    //    <strong>리라</strong>: 안녕하세요! 함께 대화를 나누기 전에, 무엇에 대해 이야기를 나누고 싶으신가요? 저와 함께 즐거운 대화를 나누어보세요.
    //  </div>
    //  <div style="height: 200px; flex-shrink: 0;"></div>
    // </div>

    // 3-2-2. 만약, chatContainer에 내용(랜더링 된 div)이 존재하고, chatContainer.scrollHeight(채팅창이 담긴 영역의 높이) 가 chatContainer.clientHeight(현재 사용자의 눈에만 보이는 채팅창들의 영역 높이)보다 크면... 쉽게 말해서 담는것 보다 넘치면...
    if (chatContainer && (chatContainer.scrollHeight > chatContainer.clientHeight)) {
      // 3-2-3. chatContainer의 scrollTop을 chatContainer.scrollHeight - chatContainer.clientHeight로 설정하여...
      const targetScrollTop = chatContainer.scrollHeight - chatContainer.clientHeight;
      // 3-2-4. 그 차이 만큼의 값(targetScrollTop)만큼을 chatContainer.scrollTo함수의 top: 패러미터에 넣어, 스크롤을 맨 아래로 이동시킨다.
      // 쉽게 말하자면 넘치는 높이값만큼 아래로 스크롤 한다고 생각하면 편하다.
      chatContainer.scrollTo({ top: targetScrollTop, behavior: 'smooth' });
    }
    // 3-2-5. 이 useEffect는 messages 배열이 변경될 때마다 실행된다.
    // 즉, 새로운 메시지가 생길 때마다 아래로 스크롤 해주는 것이다. 
  }, [messages]);

  // 4. zustand에서 설정된 전역상태로 지정된 정보를 가져온다 -> 사용자 및 세션 ID 가져오기(userStore.tsx)
  const userId = useUserStore((state) => state.userId) ?? "test_user";
  const sessionId = useUserStore((state) => state.sessionId) ?? "session_001";

  // 5. 감정 상태를 관리하는 store에서 감정 정보를 가져온다 -> 감정 상태 가져오기(emotionStore.tsx)
  const setEmotion = useEmotionStore((state) => state.setEmotion);
  const setIsProcessing = useEmotionStore((state) => state.setIsProcessing);

  // 6. 메시지를 전송하는 함수 정의 (handleSend())
  const handleSend = async () => {
    // 6-1. 입력된 메시지가 비어있거나 공백뿐이라면 전송하지 않음
    if (!userMessage.trim()) return;
    // 6-2. 메시지를 전송하기 전에, 현재 입력된 메시지를 messages 배열에 추가한다.
    const newUserMessage = { role: "user" as const, content: userMessage };
    setMessages((prev) => [...prev, newUserMessage]);
    // 6-3. 입력창을 비워준다.
    setUserMessage("");
    // 6-4. 처리중 상태 ON (예: 로딩 애니메이션 표시용)
    setIsProcessing(true);

    try {
      // 6-5. Backend에 메시지를 전송하고 응답을 받는다.
      const data = await sendMessageToLira(userId, sessionId, userMessage);
      // 6-6. 응답에서 분석된 감정값을 추출하여 상태로 저장 (추출내용 : goEmotions에서 분석된 감정라벨과 감정점수 값-> 입자 애니메이션에 사용됨)
      setEmotion({
        emotion_1st_label: (data.emotion?.emotion_1st_label ?? "neutral") as EmotionLabel,
        emotion_1st_score: data.emotion?.emotion_1st_score ?? 0,
      });
      // 6-7. Lira의 응답 메시지를 messages 배열에 추가한다.
      const liraMessage = { role: "lira" as const, content: data.output };
      setMessages((prev) => [...prev, liraMessage]);
    } catch (e) {
      // 6-8. 에러가 발생하면 콘솔에 에러를 출력하고, 사용자에게 아래의 에러 메시지를 표시한다.
      console.error("메시지 전송 실패:", e);
      const errorMessage = { role: "lira" as const, content: "응답을 가져오는 데 실패했어요. 다시 시도해주세요." };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      // 6-9. 처리중 상태 OFF (로딩 애니메이션을 숨기고 구체 애니메이션을 다시 시작)
      setIsProcessing(false);
    }
  };

  return (
    // ChatPage.tsx의 전체 페이지 영역
    <div className="chat-page-container">
      {/* 캔버스 랜더링 영역: 구체를 그리는 부분 */}
      <div className="canvas-section">
        {/* EmotionCanvasWrapper.tsx 컴포넌트를 사용하여 three.js 렌더링한다. */}
        <EmotionCanvasWrapper />
      </div>
      {/* 채팅 영역: 사용자와 Lira의 메시지를 표시하는 부분 */}
      <div className="chat-section">
        {/* 채팅창 영역 */}
        <div className="chat-history" ref={chatContainerRef}>
          {/* 메시지 목록을 렌더링 == 버블채팅풍선 랜더링 */}
          {messages.map((msg, idx) => (
            //  messages변수안에는 아래의 내용이 담겨있다.
            //  [{ role: 'user', content: '안녕' }, 
            //   { role: 'lira', content: '안녕하세요!' }]
            //  map함수를 사용하여, messages배열의 각 요소를 아래와 같이 렌더링한다.
            //  랜더링시에는 msg에 담긴 요소들을 담아서 랜더링 해준다.
            //  role: 메시지의 역할 (user 또는 lira)
            //  content: 메시지의 내용
            //  idx: 메시지의 인덱스 (react key로 사용)
            <div key={idx} className={`chat-bubble ${msg.role}`}>
              <strong>{msg.role === "user" ? "나" : "리라"}</strong>: {msg.content}
            </div>
          ))}

          {/* 스크롤 여유 공간 확보용 더미 요소 (아래로 부드럽게 스크롤 되게 함) */}
          <div style={{ height: "200px", flexShrink: 0 }} />
        </div>

        {/* 메시지 입력창 */}
        <div className="chat-input-container">
          {/* 입력창: 사용자가 메시지를 입력할 수 있는 텍스트 입력 필드 */}
          <input
            id="message-input"
            className="chat-input"
            type="text"
            // value 속성으로 userMessage 상태를 연결하여, 입력창의 값이 userMessage와 동기화되도록 한다.
            value={userMessage}

            // onChange 이벤트로 사용자가 입력하는 내용 : setUserMessage(e.target.value)로 실시간으로 userMessage 상태를 업데이트한다.
            onChange={(e) => setUserMessage(e.target.value)}

            // onKeyDown 이벤트로 Enter 키를 눌렀을 때 메시지를 전송하는 기능을 추가한다.
            // e.nativeEvent.isComposing는 입력 중인 언어의 조합 중인 상태를 확인하는 속성이다.
            // 조합중인 상태 : 예를 들어, 가 라는 한글자를 입력 시 'ㄱ'을 입력하고 'ㅏ'를 입력해야하는데 ㄱ을 입력하고 Enter를 누르면 '가'로 완성되지 않은 상태에서 메시지가 전송되는 것을 방지한다.
            // 이를 방지하기 위해 e.nativeEvent.isComposing 값을 체크한다.
            // 이 값이 true면 아직 조합 중이므로, Enter를 눌러도 메시지를 전송하지 않는다.
            // 이게 ㅎㅎ 하고 엔터하면 바로 전송되는게 아니라 그 사이의 빈틈을 확인하고 문장으로 완성되었다고 판단하면 false값을 리턴해서 메세지 전송이 가능하다.
            // 만약 e.nativeEvent.isComposing가 없다면, 'ㅎㅎ'를 입력했을경우 'ㅎ', 'ㅎ'로 말풍선이 두번 나뉘어서 전송된다.
            // (한글자 완성 여부를 확인안하고 전송하기 때문에 ㅎ 두개를 하나의 문장으로 판단하고 두번 전송된다.)
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                handleSend();
              }
            }}
            placeholder="Lira에게 말해보자!"
          />
          {/* 또는 전송 버튼 클릭 시 handleSend 함수 호출 */}
          <button onClick={handleSend} className="send-button">
            전송
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatPage;