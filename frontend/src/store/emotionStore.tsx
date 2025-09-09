// src/store/emotionStore.ts
// 역할: 감정 상태를 관리하는 Zustand 스토어로, 감정 레이블, 강도, 모드 등을 저장하고 업데이트하는 기능을 전역 컴포넌트에 제공한다.

import { create } from 'zustand';

// --- EmotionLabel, EmotionMode 타입 정의 ---
// --- 감정 레이블 타입 정의 (emotionColors.ts와 동일하게 확장) ---
// EmotionLabel, EmotionMode 타입은 아래 EmotionState 인터페이스에서 사용된다.
export type EmotionLabel =
  | 'admiration' | 'amusement' | 'anger' | 'annoyance' | 'approval'
  | 'caring' | 'confusion' | 'curiosity' | 'desire' | 'disappointment'
  | 'disapproval' | 'disgust' | 'embarrassment' | 'excitement' | 'fear'
  | 'gratitude' | 'grief' | 'joy' | 'love' | 'nervousness'
  | 'optimism' | 'pride' | 'realization' | 'relief' | 'remorse'
  | 'sadness' | 'surprise' | 'neutral';

// 감정 시각화 모드
export type EmotionMode = 'central' | 'wave';

// --- export 되는 스토어의 상태(state)와 함수(actions) 타입을 정의 ---
interface EmotionState {
  // 감정 관련 상태
  emotion_1st_label: EmotionLabel;
  emotion_1st_score: number;
  // 추가 감정 상태 -> ?로 설정하여 선택적으로 사용할 수 있다.(있을수도 없을수도 있다.)
  emotion_2nd_label?: EmotionLabel;
  emotion_2nd_score?: number;
  emotion_3rd_label?: EmotionLabel;
  emotion_3rd_score?: number;
  emotion_mode?: EmotionMode;

  // AI 작동 관련 상태
  isProcessing: boolean;

  // 상태를 업데이트할 함수들
  // => void : 내부상태만 업데이트 해주고 리턴값은 없게한다.

  // EmotionState를 업데이트하는 함수(복합변수 업데이트) 
  setEmotion: (newState: Partial<EmotionState>) => void;
  // isProcessing 상태만 업데이트(단일변수 업데이트)
  setIsProcessing: (processing: boolean) => void;
  // 모든 감정 상태를 정의된 초기값으로 리셋(전체변수 초기화)
  resetEmotion: () => void;
}

// --- Zustand 스토어 생성 ---
// 아래의 export를 통해 이 컴포넌트를 사용할 수 있게 해준다.
// Zustand에서 EmotionState 타입의 상태(store) 를 만들고, 그 상태를 변경할 수 있는 set() 함수와 초기 상태/액션들을 정의하는 부분
export const useEmotionStore = create<EmotionState>((set) => ({
  // --- 초기 상태 값 ---
  emotion_1st_label: 'neutral',
  emotion_1st_score: 0.3,
  emotion_2nd_label: 'neutral',
  emotion_2nd_score: 0,
  emotion_3rd_label: 'neutral',
  emotion_3rd_score: 0,
  emotion_mode: 'central',
  isProcessing: false,

  // --- 상태 변경 함수들 ---
  // 여러 감정 상태를 한 번에 업데이트
  // interface EmotionState에 정의된 타입의 newState형태를 패러미터로 받아서 set함수를 통해 newState -> state상태로 업데이트 해 주겠다.
  setEmotion: (newState) => set((state) => ({ ...state, ...newState })),

  // '처리 중' 상태만 업데이트
  // interface EmotionState에 정의된 타입의 processing형태를 패러미터로 받아서 set함수를 통해 isProcessing의 상태를 업데이트 해 주겠다.
  // 이때 리턴값은 interface에서 정의된 void... 즉 내부상태만 업데이트 해준다는 얘기.
  setIsProcessing: (processing) => set({ isProcessing: processing }),

  // 모든 감정 상태를 초기값으로 리셋
  resetEmotion: () => set({
    emotion_1st_label: 'neutral',
    emotion_1st_score: 0.3,
    emotion_2nd_label: 'neutral',
    emotion_2nd_score: 0,
    emotion_3rd_label: 'neutral',
    emotion_3rd_score: 0,
    isProcessing: false,
  }),
}));