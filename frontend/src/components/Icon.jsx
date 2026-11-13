// 헤더 도구용 선 아이콘. 크기와 선 굵기는 CSS(.icon, --icon-sm, --stroke-thin)가 정한다
const PATHS = {
  minus: 'M3 8h10',
  refresh: 'M13 8a5 5 0 1 1-1.5-3.5M13 2.5v3h-3',
  expand: 'M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5l-4.5 4.5M2.5 13.5l4.5-4.5',
  collapse: 'M13.5 6.5h-4v-4M2.5 9.5h4v4M9.5 6.5l4-4M6.5 9.5l-4 4',
};

export default function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}
