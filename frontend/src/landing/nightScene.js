// 랜딩 페이지 캔버스 그림: 창밖 도시의 밤과 양이성 음향 파형. 원본: 팀 랜딩 디자인 시안(sleepy-landing.html)

const maxPixelRatio = () => Math.min(window.devicePixelRatio || 1, 2);

export function sizeCanvas(canvas) {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const ratio = maxPixelRatio();
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
}

// 먼 건물에서 가까운 건물 순서: 멀수록 어둡고 불빛이 작고 흐리다
const LAYERS = [
  { n: 9, top: [0.42, 0.62], w: [0.06, 0.12], tone: 17, size: 2, gap: 6, lit: 0.16, alpha: 0.35 },
  { n: 6, top: [0.34, 0.55], w: [0.09, 0.16], tone: 22, size: 3, gap: 8, lit: 0.2, alpha: 0.6 },
  { n: 4, top: [0.36, 0.6], w: [0.12, 0.2], tone: 27, size: 4, gap: 11, lit: 0.24, alpha: 0.85 },
];

export function drawNight(canvas) {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const ratio = maxPixelRatio();
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const c = canvas.getContext('2d');
  c.scale(ratio, ratio);
  const W = rect.width;
  const H = rect.height;
  // 매번 같은 도시가 그려지도록 고정 시드 난수를 쓴다
  let seed = 23;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;

  const sky = c.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, '#0B0908');
  sky.addColorStop(0.4, '#120F0C');
  sky.addColorStop(1, '#1E1813');
  c.fillStyle = sky;
  c.fillRect(0, 0, W, H);

  LAYERS.forEach((L) => {
    for (let b = 0; b < L.n; b += 1) {
      const w = W * (L.w[0] + rnd() * (L.w[1] - L.w[0]));
      const x = (b / L.n) * W + ((rnd() - 0.5) * W) / L.n - w / 4;
      const top = H * (L.top[0] + rnd() * (L.top[1] - L.top[0]));
      c.fillStyle = `rgb(${L.tone},${L.tone - 4},${L.tone - 8})`;
      c.fillRect(x, top, w, H - top);
      for (let wy = top + L.gap; wy < H; wy += L.gap) {
        const fall = 1 - ((wy - top) / (H - top)) * 0.5;
        for (let wx = x + L.gap / 2; wx < x + w - L.size; wx += L.gap) {
          if (rnd() < L.lit * (wx < W * 0.55 ? 0.45 : 1)) {
            const cool = rnd() < 0.13;
            const a = cool
              ? Math.max(0.38, (0.5 + rnd() * 0.3) * L.alpha * fall)
              : (0.35 + rnd() * 0.65) * L.alpha * fall;
            c.fillStyle = cool
              ? `rgba(168,190,220,${a})`
              : `rgba(246,${182 + rnd() * 36},${108 + rnd() * 40},${a})`;
            c.fillRect(wx, wy, L.size, L.size + 1);
          }
        }
      }
    }
  });
}

export function drawScopes(canvases, phase) {
  canvases.forEach((canvas) => {
    if (!canvas || !canvas.width) return;
    const c = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    const kind = canvas.dataset.wave;
    const d = W / canvas.getBoundingClientRect().width;
    c.clearRect(0, 0, W, H);
    c.lineWidth = 1.6 * d;
    c.strokeStyle = kind === 'beat' ? '#E8B46A' : '#C4B7A2';
    c.beginPath();
    for (let x = 0; x <= W; x += 2) {
      const t = x / W;
      let y;
      if (kind === 'left') y = Math.sin((t * 20 + phase) * Math.PI * 2);
      else if (kind === 'right') y = Math.sin((t * 20.8 + phase * 1.04) * Math.PI * 2);
      else {
        const envelope = Math.cos((t * 0.8 + phase * 0.04) * Math.PI * 2);
        y = Math.sin((t * 20.4 + phase) * Math.PI * 2) * envelope;
      }
      const py = H / 2 + y * (H / 2 - 4 * d);
      if (x) c.lineTo(x, py);
      else c.moveTo(x, py);
    }
    c.stroke();
  });
}
