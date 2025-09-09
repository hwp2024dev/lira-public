// App.tsx
// 역할: 프론트엔드의 메인 모듈로, 사용자와의 상호작용을 처리하고 전체UI의 뼈대를 구성한다.

// import modules
import React from "react";
// react-router-dom을 사용하여 라우팅 기능을 구현.
import { Routes, Route, Navigate } from "react-router-dom";
// ChatPage 컴포넌트를 가져옵니다.
import ChatPage from "./pages/ChatPage";

// 아래의 함수는 React 애플리케이션의 진입점 역할을 한다.
export default function App() {
  return (
    // 지정된 컴포넌트 랜더링 경로.
    <Routes>
      {/* 기본 경로를 /chat으로 리다이렉트 */}
      {/* replace속성 : /로 url접속하면 바로 /chat으로 이동하고 /chat으로 이동하면, 뒤로가기를 눌러도 /chat주소를 유지한다. */}
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="/chat" element={<ChatPage />} />
    </Routes>
  );
}