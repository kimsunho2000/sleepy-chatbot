// 선 아이콘. 크기와 선 굵기는 CSS(.icon, --icon-sm, --stroke-thin)가 정한다
const PATHS = {
  close: 'M4 4l8 8M12 4l-8 8',
  refresh: 'M13 8a5 5 0 1 1-1.5-3.5M13 2.5v3h-3',
  expand: 'M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5l-4.5 4.5M2.5 13.5l4.5-4.5',
  collapse: 'M13.5 6.5h-4v-4M2.5 9.5h4v4M9.5 6.5l4-4M6.5 9.5l-4 4',
  headset: 'M3 10V8a5 5 0 0 1 10 0v2M2.5 9.5h2v4h-2zM11.5 9.5h2v4h-2z',
  chevron: 'M6 4l4 4-4 4',
  // 참고 시안의 달·보내기 아이콘(24 격자)을 16 격자로 줄인 것
  moon: 'M13.3 9.7A5.3 5.3 0 0 1 6.3 2.7a5.3 5.3 0 1 0 7 7Z',
  send: 'M8 12.7V3.3M4 7.3l4-4 4 4',
  // Lucide thumbs-up·down(24 격자)을 16 격자로 줄인 것 (ISC, Copyright (c) Lucide Contributors, https://lucide.dev/license)
  thumbsUp:
    'M4.7 6.7v8M10 3.9l-.7 2.8h3.9a1.3 1.3 0 0 1 1.3 1.7l-1.6 5.3a1.3 1.3 0 0 1-1.3 1H2.7a1.3 1.3 0 0 1-1.4-1.3V8a1.3 1.3 0 0 1 1.4-1.3h1.8a1.3 1.3 0 0 0 1.2-.8L8 1.3a2.1 2.1 0 0 1 2 2.6Z',
  thumbsDown:
    'M11.3 9.3v-8M6 12.1l.7-2.8H2.8a1.3 1.3 0 0 1-1.3-1.7l1.6-5.3a1.3 1.3 0 0 1 1.3-1h9a1.3 1.3 0 0 1 1.4 1.3V8a1.3 1.3 0 0 1-1.4 1.3h-1.8a1.3 1.3 0 0 0-1.2.8L8 14.7a2.1 2.1 0 0 1-2-2.6Z',
};

export default function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}
