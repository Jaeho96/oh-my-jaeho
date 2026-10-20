/**
 * Zoom Clips 추출 스니펫 — 브라우저 컨텍스트에서 실행할 코드의 원본(single source of truth).
 *
 * 이 파일은 node로 돌리는 스크립트가 아니다. Playwright MCP의
 * `browser_evaluate`에 넣을 함수 본문을 보관·복사하는 용도다.
 * (인증이 HttpOnly 쿠키라 페이지 안에서 fetch해야 한다 — SKILL.md 함정 ②③ 참고)
 *
 * 사용:
 *   1) browser_navigate 로 공유 링크 열기
 *   2) passcode 입력 → Confirm
 *   3) 아래 buildSnippet(shareId) 결과를 browser_evaluate 에 넣기
 *   4) 반환된 JSON 문자열을 meta.json 으로 저장
 *
 * 주의: /play/vtt 는 일부러 부르지 않는다. in-page fetch 시 브라우저가
 *       다운로드로 처리해 cwd 를 오염시킨다. VTT 는 UI 의 Transcript >
 *       Export 버튼이나, 오염을 감수하고 별도로 한 번만 받는다.
 */

function buildSnippet(shareId) {
  return `async () => {
  const base = 'https://zoomclips.zoom.us/nws/marvel/2.0/clips/share/${shareId}';
  const get = async (p) => {
    const res = await fetch(base + p, { credentials: 'include' });
    const json = await res.json();
    if (json.status === false) {
      throw new Error('API 실패 ' + p + ' → errorCode ' + json.errorCode + ' ' + json.errorMessage);
    }
    return json.result;
  };

  const [tr, ch, sf, meta] = await Promise.all([
    get('/transcript?pageType=web'),
    get('/chapters?pageType=web'),
    get('/summary-features?pageType=web'),
    get('?pageType=web'),
  ]);

  const m = meta.mediaInfo || {};
  const cues = tr.dataList || [];

  return JSON.stringify({
    _extractedAt: new Date().toISOString().slice(0, 10),
    _apiBase: 'https://zoomclips.zoom.us/nws/marvel/2.0/clips/share/{shareId}',
    shareId: '${shareId}',
    shareUrl: 'https://us06web.zoom.us/clips/share/${shareId}',
    passcodeRequired: true,
    mediaTopic: m.mediaTopic,
    ownerName: m.ownerName,
    mediaDuration: m.mediaDuration,
    createdTime: m.createdTime,
    createdTimeIso: new Date(m.createdTime).toISOString(),
    plays: (meta.statisticsInfo || {}).count,
    transcriptCueCount: cues.length,
    aiSummary: ((sf || {}).summary || {}).text,
    chapters: ch.dataList || ch.chapters || ch,
    // 녹취록 전문도 함께 — VTT 를 못 받았을 때의 대체 경로
    transcript: cues,
  });
}`;
}

// 검증용 스니펫 — 가상 스크롤 함정을 눈으로 확인할 때 쓴다.
// DOM 개수와 API 개수가 다르면 DOM 을 긁고 있었다는 뜻이다.
const VERIFY_SNIPPET = `() => ({
  domRenderedCues: document.querySelectorAll('[data-testid^="transcript-item-"]').length,
  isVirtualList: !!document.querySelector('[data-testid="transcript-virtual-list"]'),
})`;

module.exports = { buildSnippet, VERIFY_SNIPPET };

if (require.main === module) {
  const shareId = process.argv[2];
  if (!shareId) {
    console.error("usage: node extract-snippet.js <shareId>   # 스니펫을 출력한다");
    process.exit(1);
  }
  process.stdout.write(buildSnippet(shareId) + "\n");
}
