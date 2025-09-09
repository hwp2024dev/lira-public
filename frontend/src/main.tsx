// main.tsx
// 역할: React 애플리케이션의 최초 진입점으로, 전체 UI를 렌더링하고 ReactDOM을 초기화. -> app.tsx의 랜더링 지점으로 진입

// import modules
import React from "react";
// ReactDOM을 사용하여 React 애플리케이션을 브라우저에 렌더링.
import ReactDOM from "react-dom/client";
// BrowserRouter를 사용하여 브라우저에 App 컴포넌트를 렌더링.
import { BrowserRouter } from "react-router-dom";
// App 컴포넌트를 가져옵니다.
import App from "./App";
// CSS 파일을 가져옵니다. 이 파일은 전체 애플리케이션의 스타일을 정의.
import "./main.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* BrowserRouter를 사용하여 App 컴포넌트를 랜더링한다. */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);