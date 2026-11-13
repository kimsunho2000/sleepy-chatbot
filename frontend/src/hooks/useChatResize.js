import { useCallback, useEffect, useRef, useState } from 'react';

// 사용자가 정한 창 크기는 이 브라우저에만 기억한다 (없거나 막혀 있어도 기본 크기로 동작한다)
const STORAGE_KEY = 'sleeby.chat.size';

// 크기 한계와 방향키 간격은 tokens.css의 값을 읽어 쓴다 (숫자를 코드에 두지 않는다)
const readPx = (element, name) => parseFloat(getComputedStyle(element).getPropertyValue(name));
const clamp = (value, min, max) => Math.min(Math.max(value, min), Math.max(min, max));

function readLimits(element) {
  const inset = readPx(element, '--chat-inset');
  return {
    minWidth: readPx(element, '--chat-min-width'),
    maxWidth: Math.min(readPx(element, '--chat-max-width'), window.innerWidth - 2 * inset),
    minHeight: readPx(element, '--chat-min-height'),
    maxHeight: window.innerHeight - 2 * inset,
    step: readPx(element, '--resize-step'),
  };
}

function applySize(element, { width, height }) {
  if (width !== undefined) element.style.setProperty('--chat-width', `${Math.round(width)}px`);
  if (height !== undefined) element.style.setProperty('--chat-height', `${Math.round(height)}px`);
}

function saveSize(element) {
  const width = element.style.getPropertyValue('--chat-width');
  const height = element.style.getPropertyValue('--chat-height');
  try {
    if (width || height) localStorage.setItem(STORAGE_KEY, JSON.stringify({ width, height }));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 저장소를 쓸 수 없으면 이번 방문에서만 유지한다
  }
}

function restoreSize(element) {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
    if (!saved) return;
    const limits = readLimits(element);
    applySize(element, {
      width: saved.width
        ? clamp(parseFloat(saved.width), limits.minWidth, limits.maxWidth)
        : undefined,
      height: saved.height
        ? clamp(parseFloat(saved.height), limits.minHeight, limits.maxHeight)
        : undefined,
    });
  } catch {
    // 저장된 값이 깨졌거나 저장소를 쓸 수 없으면 기본 크기를 쓴다
  }
}

/**
 * 챗봇 창 크기 조절. 창이 화면 오른쪽 아래에 붙어 있어서 왼쪽/위 가장자리를 끌면 창이 커진다.
 * axis: 'corner'(가로+세로), 'left'(가로), 'top'(세로)
 */
export function useChatResize(chatRef, isEnabled) {
  const [active, setActive] = useState(null);
  const drag = useRef(null);

  useEffect(() => {
    if (isEnabled && chatRef.current) restoreSize(chatRef.current);
  }, [chatRef, isEnabled]);

  const reset = useCallback(() => {
    const element = chatRef.current;
    if (!element) return;
    element.style.removeProperty('--chat-width');
    element.style.removeProperty('--chat-height');
    saveSize(element);
  }, [chatRef]);

  const handleProps = useCallback(
    (axis) => ({
      onPointerDown: (event) => {
        const element = chatRef.current;
        if (!element || event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        const rect = element.getBoundingClientRect();
        drag.current = {
          axis,
          x: event.clientX,
          y: event.clientY,
          width: rect.width,
          height: rect.height,
          limits: readLimits(element),
        };
        setActive(axis);
      },
      onPointerMove: (event) => {
        const state = drag.current;
        const element = chatRef.current;
        if (!state || !element) return;
        const { limits } = state;
        applySize(element, {
          width:
            state.axis === 'top'
              ? undefined
              : clamp(state.width + (state.x - event.clientX), limits.minWidth, limits.maxWidth),
          height:
            state.axis === 'left'
              ? undefined
              : clamp(state.height + (state.y - event.clientY), limits.minHeight, limits.maxHeight),
        });
      },
      onPointerUp: () => {
        if (!drag.current) return;
        drag.current = null;
        setActive(null);
        if (chatRef.current) saveSize(chatRef.current);
      },
      onPointerCancel: () => {
        drag.current = null;
        setActive(null);
      },
      onDoubleClick: reset,
    }),
    [chatRef, reset],
  );

  // 키보드: 방향키로 크기를 바꾸고(왼쪽·위쪽이 커짐), Enter나 Home으로 처음 크기로 되돌린다
  const onKeyDown = useCallback(
    (event) => {
      const element = chatRef.current;
      if (!element) return;
      if (event.key === 'Enter' || event.key === 'Home') {
        event.preventDefault();
        reset();
        return;
      }
      const direction = {
        ArrowLeft: [1, 0],
        ArrowRight: [-1, 0],
        ArrowUp: [0, 1],
        ArrowDown: [0, -1],
      }[event.key];
      if (!direction) return;
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const limits = readLimits(element);
      applySize(element, {
        width: clamp(rect.width + direction[0] * limits.step, limits.minWidth, limits.maxWidth),
        height: clamp(rect.height + direction[1] * limits.step, limits.minHeight, limits.maxHeight),
      });
      saveSize(element);
    },
    [chatRef, reset],
  );

  return { active, handleProps, onKeyDown };
}
