// userStore.tsx
// 역할: zustand를 사용하여 사용자의 정보를 전역으로 관리한다.

import { create } from "zustand";

// UserState : 사용자의 정보의 타입을 정의한다.
type UserState = {
    // 사용자의 ID
    userId: string | null;
    // 세션 ID
    sessionId: string | null;
    // 사용자 ID 설정 함수 : 사용자 ID를 업데이트 하는 역할
    setUserId: (id: string) => void;
    // 세션 ID 설정 함수 : 세션 ID를 업데이트 하는 역할
    setSessionId: (id: string) => void;
    // 사용자 정보 초기화 함수 : 사용자 정보를 초기 상태로 되돌리는 역할
    resetUser: () => void;
};

// zustand의 create 함수를 사용하여 useUserStore라는 커스텀 훅을 생성한다.
// 이 훅은 UserState 타입을 기반으로 하며, userId와 sessionId를 전역 상태로 관리한다.
// 초기값은 null이지만, 실제 앱 동작중에는 다른 컴포넌트나 로직에 의해서 상태를 갱신하게 된다.
export const useUserStore = create<UserState>((set) => ({
    userId: null,
    sessionId: null,
    setUserId: (id) => set({ userId: id }),
    setSessionId: (id) => set({ sessionId: id }),
    resetUser: () => set({ userId: null, sessionId: null }),
}));