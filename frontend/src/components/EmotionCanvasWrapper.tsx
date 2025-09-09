// /EmotionCanvasWrapper.tsx

import React, { useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { useEmotionStore } from '../store/emotionStore';
import { useSpring } from '@react-spring/three';

/*
 * [개발자 노트]
 * AI의 내면 상태를 시각적으로 표현하기 위해, 이전 프론트엔드 개발 경험에서 다루었던 Three.js를 활용했습니다.
 * 초기 버전은 CPU 기반의 애니메이션으로 구현했으나, 더 높은 성능과 정교한 표현을 위해 GPU를 직접 제어하는 '커스텀 셰이더' 방식의 도입을 결정했습니다.
 *
 * 셰이더는 3D 그래픽스의 깊은 전문 분야이기에, 이 부분은 저의 명확한 설계와 감독 하에 AI 어시스턴트(Gemini)를 3D 그래픽스 전문가로 활용하여 '페어 프로그래밍' 방식으로 협업하여 구축했습니다.
 *
 * 저의 역할은 다음과 같았습니다:
 * 1. '감정'과 '생각'의 상태를 구체와 파동으로 변환하는 시각적 UX 설계 및 감독.
 * 2. AI가 생성한 GLSL 코드와 React Three Fiber 로직이 시스템 전체의 안정성과 제 설계 의도에 부합하는지를 수십 번에 걸쳐 코드 리뷰, 테스트, 디버깅하며 최종 결과물을 완성.
 *
 * 이 과정을 통해, 저는 제가 모르는 전문 분야의 문제에 부딪혔을 때, AI와 같은 최신 도구를 활용하여 해결책을 찾아내고, 그 결과물의 품질을 최종적으로 책임지는 현대적인 엔지니어의 문제 해결 능력을 체득할 수 있었습니다.
 * (인공지능은 기본적인 디버깅을 하지 못한다는 점을 인지하고 있습니다.)
 *
 * 셰이더 영역은 아래와 같습니다.
 */

// --- 1. 버텍스 셰이더 (Vertex Shader) ---
// 역할: 수천 개의 각 파티클(점)에게 이 파티클을 어디에, 얼마나 크게 그릴지 결정하는 역할을 하는 변수
const vertexShader = `
  // WebGL1 모바일 호환성 확보
  precision mediump float;

  // --- 1. 변수선언 (시간, 모양, 좌표, 색상)---

  // 1-1. uniform 타입: 변수를 모든 셰이더에서 받게 하겠다는 뜻.(모든 셰이더에서 파티클 값을 공유 받는다.)
  uniform float uTime;         // 파티클이 움직이는 시간관리 변수
  uniform float uMixFactor;    // 구체(0)와 파동(1)의 모양을 설정하는 변수 -> 0일때 구체, 1일때 파동 모양이 된다.

  // 1-2. attribute 타입: 각 파티클(점)마다 고유한 '개별 데이터'를 담는다는 뜻.
  // -> GPU는 수천 개의 파티클을 동시에 병렬 처리하기 때문에,
  //    각 파티클이 자신만의 데이터(위치, 색상 등)를 식별할 수 있도록
  //    고유 인덱스와 매핑된 attribute를 사용해야 한다.
  // -> 만약 attribute를 통해 고정 인덱스를 부여하지 않으면,
  //    모든 파티클이 동일한 데이터나 잘못된 메모리를 참조하여
  //    위치·색상 등이 뒤섞이는 혼선이 발생할 수 있다.

  // 1-3. vec3타입: 3차원 좌표를 담는다는 뜻.
  // -> 결론적으로 파티클은 각자의 개별데이터를 통해 3차원 좌표로서 아래의 정보를 가지게 된다.
  attribute vec3 spherePosition;  // 이 파티클의 '구체'일 때의 원래 좌표 (x,y,z)
  attribute vec3 wavePosition;    // 이 파티클의 '파동'일 때의 원래 좌표 (x,y,z)
  attribute vec3 particleColor;   // 이 파티클에게 지정된 고유한 파스텔톤 색상 (R,G,B)

  // 1-4. varying: 버텍스 셰이더에서 계산된 값을 프래그먼트 셰이더로 전달하는 변수 타입
  // -> CPU에서는 직접 접근할 수 없고, GPU 내부에서만 전달된다.
  // -> 여기서는 각 파티클의 색상(R,G,B)을 버텍스 셰이더에서 계산해
  //    프래그먼트 셰이더로 보내, 픽셀 단위로 색상을 칠할 때 사용한다.
  varying vec3 vColor;

  // --- 2. 함수 선언 (3D 회전 행렬 생성 함수) ---
  // 이 함수는 주어진 회전 축(axis)과 회전 각도(angle)를 기반으로,
  // 로드리게스 회전 공식을 사용하여 4x4 회전 행렬(mat4)을 계산해 반환한다.
  //
  // 핵심 개념
  // axis: 회전하고 싶은 방향 벡터 (예: y축 회전 -> vec4(0, 1, 0)) // x, y, z축
  // angle: 회전 각도(라디안 각도) -> 라디안: 180도 => 파이 라디안 , 360도 => 2파이 라디안
  // mat4: 4x4 행렬로, 3D 공간에서의 회전·이동·스케일 변환 등을 표현할 수 있음
  //
  // 직관적으로 이해하기
  // 구체를 구성하는 각 파티클의 좌표는 벡터로 표현된다.
  // 이 벡터로 표현된 좌표를 회전 공식에 넣으면, 각 파티클이 지정된 축을 기준으로
  // angle 만큼 회전된 새로운 좌표를 얻게 된다. -> 여기서 말하는 회전은 지구로 비유하자면, 자전회전이 아닌 공전회전을 뜻한다.
  // 이렇게 변환된 좌표를 GPU가 매 프레임 반영하므로,
  // 결과적으로 구체나 파동이 회전하는 애니메이션이 만들어진다.

  // mat4: 4x4 크기의 숫자 격자(행렬, Matrix)을 담는 타입.
  // rotationMatrix: main함수에서 생성된 파티클과 그 파티클의 앵글정보를 활용하여 구체형태로 회전할 수 있도록 하는 함수
  mat4 rotationMatrix(vec3 axis, float angle) {
    // 좌표 == 벡터
    // 0,0,0을 원점기준으로 하여 사인, 코사인함수를 활용, 좌표값을 수시로 갱신하여 회전시킨다.
    
    // 내용정리:
    //먼저 파티클별로 평면에서 매번 x,y의 좌표 각도를 받아서 다음 좌표로 쏴줄 각도를 예상해서 값을 보내주는거고...
    //마지막에 oc영역에서 3차원 회전함수(로드리게스 공식 -> 회전을 처리하는 함수)에 넣을값을 산출한 뒤, 값을 회전함수에 넣고 회전시킨다.

    // --- 평면(x,y) 계산영역 ---
    // 1. 회전의 '방향'을 표준화한다.
    //    어떤 길이의 축(axis)이 들어오든, normalize를 통해 크기를 1로 만들어
    //    오직 순수한 '방향' 정보만 남긴다.
    axis = normalize(axis);

    // 2. 공전 회전 각도를 '좌표 언어'로 변환한다.
    // -> 구체 <-> 웨이브 변환 과정에서도 매 프레임 올바른 회전을 적용하기 위해,
    //    현재 angle에 따른 좌표 성분을 실시간 계산한다.
    // -> 수평 시계방향으로 회전한다.
    float s = sin(angle); // 회전 후 세로(y) 방향 성분 -> 이후에 회전할 세로 좌표를 설정하는 각도값(0~1 범위)
    float c = cos(angle); // 회전 후 가로(x) 방향 성분 -> 이후에 회전할 가로 좌표를 설정하는 각도값(0~1 범위)

    // --- 3D 회전 행렬(x,y,z) 계산 영역 ---
    // 3. 회전 보정 계수
    // -> cos(angle)이 1이면, 수직 즉 (0,y)이므로... 회전이 전혀없는 상태가 된다.
    // -> cos(angle)이 0이면, 수평 즉 (x,0)이므로... 회전 상태가 된다.
    // -> 즉, x축에서 파티클이 얼마나 벗어났는지를 0~1 범위로 수치화한 값
    //    이후 행렬 계산에서, 회전 축 주변의 벡터 성분을 비율에 맞게 섞는 데 사용됨
    float oc = 1.0 - c;
    
    // 로드리게스 회전 공식 활용
    // 4x4 회전 행렬을 구성하여, 벡터를 주어진 축으로 angle만큼 회전시킬 수 있게 함 -> 끝에 열: 이동을 담당. 
    return mat4(oc * axis.x * axis.x + c,           oc * axis.x * axis.y - axis.z * s,  oc * axis.z * axis.x + axis.y * s,  0.0, // 회전후의 x축 방향
                oc * axis.x * axis.y + axis.z * s,  oc * axis.y * axis.y + c,           oc * axis.y * axis.z - axis.x * s,  0.0, // 회전후의 y축 방향
                oc * axis.z * axis.x - axis.y * s,  oc * axis.y * axis.z + axis.x * s,  oc * axis.z * axis.z + c,           0.0, // 회전후의 z축 방향
                0.0,                                0.0,                                0.0,                                1.0); // 위치이동
  }

  // 위에서 만든 도구를 사용하여, 특정 점(v)을 특정 축(axis)으로 특정 각도(angle)만큼 실제로 회전시켜준다
  vec3 rotate(vec3 v, vec3 axis, float angle) {
    mat4 m = rotationMatrix(axis, angle);
    return (m * vec4(v, 1.0)).xyz;
  }

  // --- 메인 요리 과정 ---
  // 이 main() 함수가 수천 개의 모든 파티클 각각에 대해 한 번씩 동시에 실행된다.
  void main() {
    // 먼저, 파티클의 고유색상을 넘겨준다.
    vColor = particleColor;

    // 1단계: '파동'의 움직임을 만든다.
    // 이 파티클의 기본 파동 위치(wavePosition)에, 시간에 따라 계속 변하는 sin() 값을 더해서 출렁이는 움직임을 만든다.
    float waveMovement = sin(wavePosition.x * 2.0 + uTime) * 0.3;
    vec3 animatedWavePoint = vec3(wavePosition.x, wavePosition.y + waveMovement, wavePosition.z);
    
    // 2단계: '모양'을 바꿔준다.
    // uMixFactor가 0이면 100% 구체, 1이면 100% 파동이 된다.
    vec3 morphedPosition = mix(spherePosition, animatedWavePoint, uMixFactor);

    // 3단계: 전체를 '회전'시킵니다.
    // 방금 만든 '모양'을 y축(vec3(0.0, 1.0, 0.0))을 기준으로 시간에 따라 천천히 회전시킨다.
    vec3 rotatedPosition = rotate(morphedPosition, vec3(0.0, 1.0, 0.0), uTime * 0.1);

    // --- 최종 명령 ---
    // 마지막으로, "이 파티클을 최종적으로 화면 어디에, 얼마나 크게 그릴지" GPU에게 명령한다.
    vec4 modelPosition = modelMatrix * vec4(rotatedPosition, 1.0);
    vec4 viewPosition = viewMatrix * modelPosition;
    gl_Position = projectionMatrix * viewPosition; // 최종 위치 결정!
    gl_PointSize = 2.5;                            // 최종 크기 결정!
  }
`;

// --- 2. 프래그먼트 셰이더 (Fragment Shader) ---
// 역할: 각 파티클(점)이 화면에 그려질 때, 그 점의 '색깔'을 무엇으로 칠할지 결정하는 역할을 한다.
const fragmentShader = `
  // WebGL1 모바일 호환성 확보
  precision mediump float;
  
  // 아까 버텍스 셰이더의 '우편배달부(varying)'가 가져온 색상 정보를 받는다.
  varying vec3 vColor;

  // 이 main() 함수가 화면에 그려질 모든 점(픽셀) 각각에 대해 한 번씩 실행된다.
  void main() {
    // 이 점(픽셀)의 최종 색깔은, '우편배달부'가 가져온 바로 그 색깔(vColor)이다! 라고 GPU에게 명령한다.
    gl_FragColor = vec4(vColor, 1.0); // 마지막 1.0은 투명도를 의미. (불투명)
  }
`;

// EmotionParticles의 컴포넌트 영역
// --- 1. 데이터를 담는 변수 영역 ---
const EmotionParticles: React.FC = () => {
  // useRef 훅을 사용하여, 셰이더를 참조할 수 있는 레퍼런스를 생성한다.
  const shaderRef = useRef<THREE.ShaderMaterial>(null!);
  // zustand의 감정 상태를 가져온다.
  const isProcessing = useEmotionStore((state) => state.isProcessing);

  // 구체, 파동의 '기본틀' 위치 및 '파스텔톤 색상'을 미리 계산
  const { spherePositions, wavePositions, pastelColors } = useMemo(() => {
    // 생성할 점의 개수
    const count = 2000;
    // 각 파티클의 위치와 색상을 담을 배열을 생성
    const sphereArr = new Float32Array(count * 3);
    const waveArr = new Float32Array(count * 3);
    const colorArr = new Float32Array(count * 3);

    // 파스텔톤 색상 팔레트
    const colorPalette = [
      new THREE.Color("#FFDDC1"), new THREE.Color("#FFABAB"),
      new THREE.Color("#DDFFDD"), new THREE.Color("#A7C7E7"),
      new THREE.Color("#F1CBFF"),
    ];

    // 구체 위치 및 색상 계산(출처 코드 응용)
    // 출처: https://3dcodekits.tistory.com/entry/Even-distribution-of-points-on-a-sphere-with-count-control-Threejs?utm_source=chatgpt.com
    const offset = 2 / count;
    // 점들이 구 표면에 균등하게 퍼지도록 회전 간격을 설정
    const increment = Math.PI * (3 - Math.sqrt(5));
    // 위에 설정한 파티클 개수만큼 반복
    for (let i = 0; i < count; i++) {
      // 세로 y좌표: -1~1 범위를 균일하게 샘플링(극점부터 적도까지 고르게 분포)               
      const y = i * offset - 1 + (offset / 2);
      // y좌표에 해당하는 반지름 r 계산: 구의 표면에서 y좌표에 해당하는 원의 반지름
      const r = Math.sqrt(1 - y * y);
      // 같은 높이에 있는 점들이 한쪽으로 몰리지 않게, 회전 각도를 조금씩 다르게 해 준다.             
      const phi = i * increment;
      // x, z 좌표 계산: 구의 표면에서 각도에 따라 x, z좌표를 계산
      const x = Math.cos(phi) * r;
      const z = Math.sin(phi) * r;
      // 구의 전체 크기 스케일(반지름에 해당)
      const scale = 2.5;
      // i번째 파티클의 x값 기록
      sphereArr[i * 3] = x * scale;
      // i번째 파티클의 y값 기록
      sphereArr[i * 3 + 1] = y * scale;
      // i번째 파티클의 z값 기록
      sphereArr[i * 3 + 2] = z * scale;

      // 팔레트에서 임의의 파스텔톤 색상 선택
      const randomColor = colorPalette[Math.floor(Math.random() * colorPalette.length)];
      // i번째 파티클의 R 채널
      colorArr[i * 3] = randomColor.r;
      // i번째 파티클의 G 채널
      colorArr[i * 3 + 1] = randomColor.g;
      // i번째 파티클의 B 채널
      colorArr[i * 3 + 2] = randomColor.b;
    }

    // 파동 위치 계산
    // 파동 애니메이션을 구현 하기 위해 아래의 변수들을 설정

    // 파동의 줄 : 5줄
    const numLines = 5;
    // 각 줄마다 파티클 개수 설정
    const particlesPerLine = count / numLines;
    for (let i = 0; i < count; i++) {
      // lineIndex: 현재 파티클이 속한 줄의 인덱스
      const lineIndex = Math.floor(i / particlesPerLine);
      // indexOnLine: 현재 파티클이 속한 줄에서의 인덱스
      const indexOnLine = i % particlesPerLine;
      // x좌표: 각 줄의 파티클이 고르게 퍼지도록 0~5 범위로 설정
      const x = (indexOnLine / particlesPerLine) * 5 - 2.5;
      // y좌표: 각 줄의 위치를 -0.3 ~ 0.3 범위로 설정하여 줄 간격을 조정
      const y = lineIndex * 0.3 - (numLines * 0.3) / 2;
      // waveArr에 3차원 좌표(x, y, z)를 순서대로 넣는다.
      waveArr[i * 3] = x;
      waveArr[i * 3 + 1] = y;
      waveArr[i * 3 + 2] = 0;
    }
    // 최종적으로 구체 위치, 파동 위치, 파스텔톤 색상 배열을 반환
    return { spherePositions: sphereArr, pastelColors: colorArr, wavePositions: waveArr };
  }, []);

  // react-spring으로 mixFactor 값을 부드럽게 애니메이션
  const { mixFactor } = useSpring({
    // mixFactor를 통해 구체 <-> 파동 모양을 전환
    mixFactor: isProcessing ? 1 : 0,
    // 변환시 애니메이션 물리 효과의 조정값
    config: { mass: 2, tension: 170, friction: 26 },
  });

  // 셰이더에 전달할 초기 uniform 값들과 파티클 위치 attribute
  const shaderArgs = useMemo(() => ({
    // 셰이더가 사용할 uniform 변수들
    uniforms: {
      // uTime: 시간 값. 애니메이션을 만들 때 프레임마다 증가시킨다.
      uTime: { value: 0 },
      // uMixFactor: 구체와 파동의 모양을 결정하는 값. 0이면 구체, 1이면 파동.
      uMixFactor: { value: 0 },
    },
    // 셰이더 코드
    // vertexShader: 버텍스 셰이더 코드
    vertexShader,
    // fragmentShader: 프래그먼트 셰이더 코드  
    fragmentShader,
    // transparent: 배경이 투명하도록 설정.
    transparent: true,
    // depthWrite: 투명효과 비활성화.
    depthWrite: false,
  }), []);

  // useFrame은 이제 시간(uTime)과 애니메이션 값(uMixFactor)을 GPU로 보내는 역할만 수행
  // 매 프레임마다 실행되는 함수.
  useFrame(({ clock }) => {
    if (shaderRef.current) {
      // uTime에 현재 경과 시간을 넣어 애니메이션이 움직이게 합니다.
      shaderRef.current.uniforms.uTime.value = clock.getElapsedTime();
      // uMixFactor에 현재 전환 비율을 넣어 구체 <-> 파동 변화 반영.
      shaderRef.current.uniforms.uMixFactor.value = mixFactor.get();
    }
  });
  // --- 2. 데이터 처리 함수 영역 ---
  return (
    // points 태그 : 점을 그리는 컨테이너
    <points>
      {/* bufferGeometry 태그 : point 좌표 정보 -> <bufferAttribute>들을 담는 태그 */}
      <bufferGeometry>
        {/* bufferAttribute는 파티클(점)의 좌표 데이터를 GPU에 넘기는 역할을 한다. */}
        {/* attach: 이 속성은 셰이더에서 사용될 때, 어떤 이름으로 사용될지를 정의한다. */}
        {/* args: [좌표 데이터 배열, 요소 수]]. --> Float32Array(점들의 좌표가 전부 들어가 있다), 3(그 좌표를 세개씩 끊어서 쓰겠다))*/}
        {/* -> 각각의 속성은 Float32Array로 전달되며, 3개의 값(x, y, z)로 구성된다. */}
        {/* 각 좌표데이터 배열들 -> spherePositions : 구체의 위치, wavePositions: 파동의 위치, pastelColors: 파티클 색상을 나타낸다. */}
        <bufferAttribute attach="attributes-position" args={[spherePositions, 3]} />
        <bufferAttribute attach="attributes-spherePosition" args={[spherePositions, 3]} />
        <bufferAttribute attach="attributes-wavePosition" args={[wavePositions, 3]} />
        <bufferAttribute attach="attributes-particleColor" args={[pastelColors, 3]} />
      </bufferGeometry>
      {/* shaderMaterial을 작성된 셰이더(위치계산 코드)를 사용한다. */}
      {/* args: 셰이더의 초기, uniform 값들과 셰이더 코드들을 전달한다. -> 초기설정값*/}
      {/* ref: 셰이더를 참조하기 위한 참조 값으로, useFrame에서 업데이트할 때 사용된다. -> 초기설정 이후 갱신값*/}
      <shaderMaterial ref={shaderRef} args={[shaderArgs]} />
    </points>
  );
};

// export default로 외부에서 import할 수 있는 최상위 컴포넌트 (감정 입자 렌더링의 진입점 역할)
const EmotionCanvasWrapper: React.FC = () => {
  return (
    // Canvas: @react-three/fiber의 핵심 컨테이너로, 3D 씬을 렌더링할 수 있는 공간을 제공한다.
    // camera: 3D 카메라의 위치와 시야각(fov)를 지정한다. 여기선 z축 5만큼 떨어진 위치에서 바라보게 설정.
    <Canvas camera={{ position: [0, 0, 5], fov: 75 }}>

      {/* ambientLight: 장면 전체를 은은하게 밝히는 광원 (전체적인 조명 역할)
      intensity: 빛의 밝기. 1.5로 다소 밝게 설정하여 입자들이 전체적으로 보이게 함 */}
      <ambientLight intensity={1.5} />

      {/* pointLight: 한 점에서 퍼지는 빛을 표현 (전방에서 비추는 스포트라이트 느낌)
      position: 3D 공간 내에서 광원의 위치를 지정 (10,10,10에서 비춘다)
      intensity: 빛의 밝기 (0.5로 설정하여 보조 조명처럼 사용) */}
      <pointLight position={[10, 10, 10]} intensity={0.5} />

      {/* EmotionParticles: 감정 상태에 따라 입자 시각화 애니메이션을 수행하는 핵심 컴포넌트
      useEmotionStore의 감정값에 따라 색상과 움직임이 바뀌며, 셰이더 기반의 렌더링과 연결된다. */}
      <EmotionParticles />

      {/* OrbitControls: 마우스를 이용해 3D 공간을 회전, 확대, 이동할 수 있게 해주는 컨트롤러
      사용자에게 3D 씬을 탐색할 수 있는 자유도를 부여한다. */}
      <OrbitControls />
    </Canvas>
  );
};

// 임포팅한 코드 요청이 들어올 경우 EmotionCanvasWrapper 컴포넌트를 export 해준다.
export default EmotionCanvasWrapper;