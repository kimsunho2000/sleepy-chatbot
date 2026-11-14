import Icon from './Icon';

export default function ThemeToggle({ theme }) {
  const label = theme.isDark ? '밝은 화면' : '어두운 화면';
  return (
    <button
      type="button"
      className="ghost-btn"
      aria-label={`${label}으로 바꾸기`}
      onClick={theme.toggle}
    >
      <Icon name={theme.isDark ? 'sun' : 'moon'} />
      <span>{label}</span>
    </button>
  );
}
