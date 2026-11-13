// 챗봇을 띄워 보는 데모용 회사 홈페이지. 원본: 팀 랜딩 디자인 시안(sleepy-landing.html)
// 실제 서비스에서는 회사 홈페이지에 챗봇을 iframe으로 넣으므로, 이 페이지는 시연과 확인용이다.
import { useEffect, useRef, useState } from 'react';
import './landing.css';
import { drawNight, drawScopes, sizeCanvas } from './nightScene';

const IS_DEMO = import.meta.env.VITE_DEMO === 'true';
const TONE_SECONDS = 30;
const PLAY_LABEL = '이어폰을 끼고 원리 들어 보기';

const SUGGESTIONS = [
  ['스마트폰이나 앱이 꼭 필요한가요?', '스마트폰이나 앱이 꼭 필요한가요?'],
  ['옆으로 누워도 불편하지 않나요?', '옆으로 누워도 불편하지 않나요?'],
  ['양이성 음향이란 무엇인가요?', '양이성 음향이 뭔가요?'],
];

const FAQ = [
  [
    '스마트폰이나 전용 앱이 필요한가요?',
    '아니요. 스마트폰 연결이나 앱 설치 없이 사용할 수 있어요. 귀마개를 충전 케이스에서 꺼내면 자동으로 작동해요.',
  ],
  [
    '잠잘 때 옆으로 누워도 불편하지 않나요?',
    '착용감은 귀 모양과 자세에 따라 다를 수 있어요. 옆으로 누웠을 때 불편하다면 착용 위치를 조정하거나 잠시 빼 주세요.',
  ],
  [
    '잠귀가 밝은 편인데, 주변 소리가 들리나요?',
    '슬리비에는 액티브 노이즈 캔슬링 기능이 없고, 외부 소리를 완전히 차단하는 제품도 아니에요. 일반 귀마개를 착용했을 때처럼 주변 소리가 작게 들릴 수 있어요.',
  ],
  [
    '매일 사용해도 괜찮나요?',
    '네. 착용감에 불편함이 없다면 필요할 때 반복해서 사용하셔도 괜찮아요. 양이성 음향에 대한 반응과 사용 경험에는 개인차가 있을 수 있어요.',
  ],
  [
    '충전은 어떻게 하나요?',
    '슬리비를 케이스에 넣으면 충전돼요. 케이스는 USB-C 케이블로 충전하고, 충전 중에는 흰색 LED가 깜박이다가 완료되면 계속 켜져 있어요.',
  ],
];

const NAV = [
  ['#about', '회사 소개'],
  ['#tech', '기술'],
  ['#product', '제품'],
  ['#/chat', '챗봇 단독 화면'],
  ['#admin', '관리'],
];

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function ArrowIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function MoonIcon({ strokeWidth = '1.8' }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
    </svg>
  );
}

export default function Landing({ onAsk, onOpenChat }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [deskText, setDeskText] = useState('');
  const [isPlaying, setIsPlaying] = useState(false);
  const [notifyEmail, setNotifyEmail] = useState('');
  const [notifyMessage, setNotifyMessage] = useState('');
  const [toast, setToast] = useState('');
  const nightRef = useRef(null);
  const scopeRefs = useRef([]);
  const logRef = useRef(null);
  const audioRef = useRef({ ctx: null, nodes: null, raf: 0, stopTimer: 0, phase: 0 });
  const toastTimer = useRef(0);

  const showToast = (text) => {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 2600);
  };

  // 창밖 도시와 소리 파형은 캔버스로 그리고, 창 크기가 바뀌면 다시 그린다
  useEffect(() => {
    const redraw = () => {
      drawNight(nightRef.current);
      scopeRefs.current.forEach((canvas) => sizeCanvas(canvas));
      drawScopes(scopeRefs.current, audioRef.current.phase);
    };
    redraw();
    let timer = 0;
    const onResize = () => {
      clearTimeout(timer);
      timer = setTimeout(redraw, 200);
    };
    window.addEventListener('resize', onResize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  // 밤의 시계가 화면에 들어오면 순서대로 켜진다
  useEffect(() => {
    const log = logRef.current;
    if (!log || prefersReducedMotion() || !('IntersectionObserver' in window)) return undefined;
    if (log.getBoundingClientRect().top <= window.innerHeight) return undefined;
    log.classList.add('is-waiting');
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        log.classList.replace('is-waiting', 'is-lit');
        observer.disconnect();
      },
      { rootMargin: '0px 0px -25% 0px' },
    );
    observer.observe(log);
    return () => observer.disconnect();
  }, []);

  const stopTone = () => {
    const audio = audioRef.current;
    if (!audio.nodes) return;
    const now = audio.ctx.currentTime;
    const { gain, left, right } = audio.nodes;
    gain.gain.cancelScheduledValues(now);
    gain.gain.setTargetAtTime(0, now, 0.3);
    setTimeout(() => {
      left.stop();
      right.stop();
    }, 1500);
    audio.nodes = null;
    clearTimeout(audio.stopTimer);
    cancelAnimationFrame(audio.raf);
    setIsPlaying(false);
  };

  // 페이지를 떠나면 시연음과 알림 타이머를 정리한다
  useEffect(
    () => () => {
      const audio = audioRef.current;
      clearTimeout(toastTimer.current);
      clearTimeout(audio.stopTimer);
      cancelAnimationFrame(audio.raf);
      audio.ctx?.close();
      audio.ctx = null;
      audio.nodes = null;
    },
    [],
  );

  const playTone = () => {
    if (isPlaying) {
      stopTone();
      return;
    }
    const audio = audioRef.current;
    audio.ctx = audio.ctx ?? new (window.AudioContext || window.webkitAudioContext)();
    audio.ctx.resume();
    const gain = audio.ctx.createGain();
    gain.gain.value = 0;
    gain.connect(audio.ctx.destination);
    const makeTone = (frequency, pan) => {
      const oscillator = audio.ctx.createOscillator();
      oscillator.frequency.value = frequency;
      const panner = audio.ctx.createStereoPanner();
      panner.pan.value = pan;
      oscillator.connect(panner).connect(gain);
      oscillator.start();
      return oscillator;
    };
    audio.nodes = { gain, left: makeTone(200, -1), right: makeTone(208, 1) };
    gain.gain.setTargetAtTime(0.05, audio.ctx.currentTime, 0.8);
    setIsPlaying(true);
    if (!prefersReducedMotion()) {
      const loop = () => {
        audio.phase += 0.012;
        drawScopes(scopeRefs.current, audio.phase);
        audio.raf = requestAnimationFrame(loop);
      };
      loop();
    }
    audio.stopTimer = setTimeout(stopTone, TONE_SECONDS * 1000);
  };

  const submitDesk = (event) => {
    event.preventDefault();
    const text = deskText.trim();
    if (!text) return;
    setDeskText('');
    onAsk(text);
  };

  const submitNotify = (event) => {
    event.preventDefault();
    if (!EMAIL_PATTERN.test(notifyEmail.trim())) {
      setNotifyMessage('이메일 주소를 다시 확인해 주세요.');
      return;
    }
    setNotifyMessage('신청을 받았어요. 데모라서 실제로 저장되지는 않아요.');
    setNotifyEmail('');
  };

  const onNavClick = (event, href) => {
    setIsMenuOpen(false);
    if (href === '#admin') {
      event.preventDefault();
      showToast('관리 화면은 데모에서 준비 중이에요');
    }
  };

  const navLinks = NAV.map(([href, label]) => (
    <a key={href} href={href} onClick={(event) => onNavClick(event, href)}>
      {label}
    </a>
  ));

  return (
    <div className="landing">
      <p className="demo-bar">
        {IS_DEMO
          ? '챗봇 시연용 데모 · 실제 슬리피 홈페이지가 아니며, 답변은 임시 자료 기반이고 문의는 실제로 전송되지 않아요'
          : '챗봇 시연용 페이지 · 실제 슬리피 홈페이지가 아니에요'}
      </p>

      <header className="site-header">
        <div className="wrap">
          <a className="wordmark" href="#top" aria-label="SLEEPY 처음으로">
            SLEEPY
          </a>
          <nav className="nav" aria-label="주요 메뉴">
            {navLinks}
          </nav>
          <button
            className="menu-btn"
            type="button"
            aria-label="메뉴"
            aria-expanded={isMenuOpen}
            aria-controls="mobile-nav"
            onClick={() => setIsMenuOpen((value) => !value)}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M4 9h16M4 15h16" />
            </svg>
          </button>
        </div>
        <nav
          className={`mobile-nav ${isMenuOpen ? 'is-open' : ''}`}
          id="mobile-nav"
          aria-label="모바일 메뉴"
        >
          {navLinks}
        </nav>
      </header>

      <main id="top">
        <section className="hero turndown" aria-labelledby="hero-title">
          <canvas className="night" ref={nightRef} aria-hidden="true" />
          <div className="mullions" aria-hidden="true" />
          <div className="lamp-glow" aria-hidden="true" />
          <div className="reflect" aria-hidden="true" />
          <div className="ceiling" aria-hidden="true" />

          <div className="wrap">
            <h1 id="hero-title" className="display">
              앱 없이,
              <br />
              귀에 꽂기만 <span>하세요</span>
            </h1>
            <p className="hero-sub">
              디지털 귀마개 슬리비는 약물이 아닌 소리, 양이성 음향으로 잠드는 밤을 돕습니다.
            </p>

            <div className="desk">
              <form className="desk-form" onSubmit={submitDesk}>
                <label className="sr-only" htmlFor="desk-input">
                  슬리비에 대해 질문하기
                </label>
                <input
                  id="desk-input"
                  type="text"
                  placeholder="슬리비에 대해 무엇이든 물어보세요"
                  autoComplete="off"
                  maxLength={500}
                  value={deskText}
                  onChange={(event) => setDeskText(event.target.value)}
                />
                <button className="ask-btn" type="submit" aria-label="질문 보내기">
                  <span>물어보기</span>
                  <ArrowIcon />
                </button>
              </form>
              <div className="suggest">
                {SUGGESTIONS.map(([question, label]) => (
                  <button
                    key={question}
                    className="lp-pill"
                    type="button"
                    onClick={() => onAsk(question)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="section problem" id="problem" aria-labelledby="problem-title">
          <div className="wrap">
            <h2 id="problem-title" className="section-title display">
              잠들지 못하는 밤은
              <br />
              이렇게 흘러갑니다
            </h2>
            <ol className="night-log" ref={logRef}>
              <li>
                <time dateTime="23:40">23:40</time>
                <div>
                  <h3>불을 끄고 누웠지만, 정신은 또렷합니다</h3>
                  <p>몸은 피곤한데 잠이 오지 않아 한참을 뒤척입니다.</p>
                </div>
              </li>
              <li>
                <time dateTime="01:15">01:15</time>
                <div>
                  <h3>수면제를 떠올리지만, 매일 기댈까 걱정됩니다</h3>
                  <p>약이 아닌 다른 방법은 없을지 고민하게 됩니다.</p>
                </div>
              </li>
              <li>
                <time dateTime="03:02">03:02</time>
                <div>
                  <h3>결국 휴대폰을 켭니다</h3>
                  <p>수면 앱과 영상을 찾다가 화면 불빛에 오히려 잠이 달아납니다.</p>
                </div>
              </li>
            </ol>
          </div>
        </section>

        <section className="section feature" id="feature" aria-labelledby="feature-title">
          <div className="wrap">
            <div>
              <h2 id="feature-title" className="section-title display">
                소리만으로, 설정 없이
              </h2>
              <p className="lead">
                슬리비는 귀마개 안에 양이성 음향을 담았습니다. 휴대폰도, 앱도, 버튼도 필요 없습니다.
              </p>
            </div>

            <div className="listen" id="tech">
              <div className="listen-copy">
                <h3>
                  양쪽 귀에 조금 다른 소리,
                  <br />그 사이의 느린 박동
                </h3>
                <p>
                  왼쪽 귀에 200Hz, 오른쪽 귀에 208Hz를 들려주면 그 차이인 8Hz의 박동감을 느끼게
                  됩니다. 이것이 양이성 음향입니다.
                </p>
                <button className="play" type="button" aria-pressed={isPlaying} onClick={playTone}>
                  <i>
                    <svg
                      className="ic-play"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path d="M8 5.5v13l11-6.5z" />
                    </svg>
                    <svg
                      className="ic-stop"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <rect x="7" y="7" width="10" height="10" rx="1.5" />
                    </svg>
                  </i>
                  <span>{isPlaying ? '멈추기' : PLAY_LABEL}</span>
                </button>
                <p className="listen-note">
                  원리를 보여 주는 시연음이며 실제 슬리비의 소리와는 다릅니다. 작은 소리로 30초 동안
                  재생됩니다.
                </p>
              </div>
              <dl className="scope" aria-label="왼쪽 200Hz, 오른쪽 208Hz, 그 차이 8Hz의 박동">
                {[
                  ['left', '왼쪽 귀', '200Hz'],
                  ['right', '오른쪽 귀', '208Hz'],
                  ['beat', '느끼는 박동', '8Hz'],
                ].map(([wave, label, value], index) => (
                  <div key={wave} className={`scope-row ${wave === 'beat' ? 'beat' : ''}`}>
                    <dt>
                      {label}
                      <b>{value}</b>
                    </dt>
                    <dd>
                      <canvas
                        data-wave={wave}
                        ref={(element) => {
                          scopeRefs.current[index] = element;
                        }}
                        aria-hidden="true"
                      />
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            <ul className="answers" id="product">
              <li>
                <h3>작고 일정한 소리</h3>
                <p>
                  잠이 오지 않는 밤에도 슬리비는 작은 음량으로 재생되고 볼륨을 따로 조절하지
                  않습니다. 소리에 집중해도, 신경 쓰지 않고 잠들어도 괜찮습니다.
                </p>
              </li>
              <li>
                <h3>약물이 아닌 양이성 음향</h3>
                <p>
                  약에 기대지 않고, 양쪽 귀에 서로 다른 주파수를 들려주는 원리를 활용합니다. 소리로
                  소음을 덮는 백색소음과도 다릅니다.
                </p>
              </li>
              <li>
                <h3>꺼내면 바로 작동</h3>
                <p>
                  스마트폰 연결이나 앱 설치가 없습니다. 충전 케이스에서 꺼내면 자동으로 작동하니
                  화면을 볼 일이 없습니다.
                </p>
              </li>
            </ul>

            <div className="ritual">
              <p className="display">
                <span>케이스에서 꺼내고,</span>
                <br />
                <span>귀에 꽂고,</span>
                <br />
                <em>눈을 감으세요.</em>
              </p>
              <p className="in-box">
                구성품 · 본체, 충전 케이스, USB-C 케이블, S/M/L 이어팁, 사용 설명서
              </p>
            </div>
          </div>
        </section>

        <section className="section faq" id="faq" aria-labelledby="faq-title">
          <div className="wrap faq-grid">
            <div className="faq-side">
              <h2 id="faq-title" className="section-title display">
                자주 묻는 질문
              </h2>
              <p className="lead">
                여기 없는 질문은 안내 도우미가 답해 드려요. 자료에 없는 내용은 담당자에게 연결해
                드립니다.
              </p>
              <button className="text-link" type="button" onClick={onOpenChat}>
                안내 도우미에게 묻기
                <ArrowIcon />
              </button>
            </div>
            <div className="faq-list">
              {FAQ.map(([question, answer], index) => (
                <details key={question} name="faq" open={index === 0}>
                  <summary>
                    {question}
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      aria-hidden="true"
                    >
                      <path d="M12 5v14M5 12h14" />
                    </svg>
                  </summary>
                  <p>{answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="section cta" id="cta" aria-labelledby="cta-title">
          <div className="wrap">
            <h2 id="cta-title" className="section-title display">
              오늘 밤 궁금한 것,
              <br />
              지금 물어보세요
            </h2>
            <p className="lead">
              사용법, 착용감, 충전까지. 슬리비 안내 도우미가 자료를 바탕으로 답해 드려요.
            </p>
            <button className="cta-btn" type="button" onClick={onOpenChat}>
              <MoonIcon />
              안내 도우미와 대화하기
            </button>

            <form className="notify" noValidate onSubmit={submitNotify}>
              <label htmlFor="notify-email">출시 소식은 이메일로 받아 보세요</label>
              <div className="notify-row">
                <input
                  id="notify-email"
                  type="email"
                  placeholder="name@example.com"
                  autoComplete="email"
                  value={notifyEmail}
                  onChange={(event) => setNotifyEmail(event.target.value)}
                />
                <button type="submit">알림 신청</button>
              </div>
              <p className="notify-msg" role="status" aria-live="polite">
                {notifyMessage}
              </p>
            </form>
          </div>
        </section>
      </main>

      <footer className="site-footer" id="about">
        <div className="wrap">
          <span className="wordmark">SLEEPY</span>
          <p>SLEEPY는 양이성 음향을 활용한 디지털 귀마개 슬리비(SLEEBY)를 만듭니다.</p>
          <p>이 페이지는 챗봇 시연용 데모이며 실제 서비스가 아닙니다.</p>
        </div>
      </footer>

      <div className={`lp-toast ${toast ? 'is-on' : ''}`} role="status" aria-live="polite">
        {toast}
      </div>
    </div>
  );
}
