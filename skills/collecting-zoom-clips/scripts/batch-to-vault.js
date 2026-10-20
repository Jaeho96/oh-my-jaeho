#!/usr/bin/env node
/**
 * clips-batch.json (browser_evaluate 결과) → 볼트 파일 3종 × N
 *
 * 사용:
 *   node batch-to-vault.js <clips-batch.json> [--dry]
 *
 * 각 clip 마다 다음을 만든다.
 *   <원본 폴더>/<basename>.vtt          transcript 배열 → WEBVTT
 *   <원본 폴더>/<basename>.txt          평문 (헤더 + "MM:SS  본문")
 *   <원본 폴더>/<basename>_meta.json    챕터·AI요약·메타 (녹취록 본문은 제외)
 *
 * 원본 폴더는 kind 로 정한다.
 *   발제 · QA     → 프론트_RoundN/발제/원본/
 *   라이브세션    → 프론트_RoundN/멘토링&라이브 세션/원본/
 *
 * ⚠️ chapters 는 Zoom AI 생성물이고 R8 검증에서 타임스탬프가 어긋났다.
 *    meta.json 에 원본 보존만 하고 노트 본문에는 쓰지 않는다 (SKILL.md 참고).
 */

const fs = require("node:fs");
const path = require("node:path");

const VAULT =
  process.env.ZOOM_CLIPS_VAULT_DIR ||
  path.join(require("node:os").homedir(), "Documents/Obsidian Vault/나의 지식그래프/루퍼스/프론트_멘토링");
const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

const [batchPath, ...flags] = process.argv.slice(2);
const DRY = flags.includes("--dry");
if (!batchPath) {
  console.error("usage: node batch-to-vault.js <clips-batch.json> [--dry]");
  process.exit(1);
}

/** 라운드 폴더는 날짜 접미사가 붙은 것도 있어 접두어로 찾는다 */
function roundDir(round) {
  const hit = fs
    .readdirSync(VAULT)
    .find((d) => d === `프론트_Round${round}` || d.startsWith(`프론트_Round${round} `));
  if (!hit) throw new Error(`Round${round} 폴더를 못 찾음`);
  return path.join(VAULT, hit);
}

function targetOf(c) {
  const root = roundDir(c.round);
  if (c.kind === "라이브세션") {
    const base = `프론트_${c.mentor}_Live_Session_${c.mmdd}`;
    return { dir: path.join(root, "멘토링&라이브 세션", "원본"), base };
  }
  const base = `Round${c.round}_${c.kind}`; // 발제 / QA
  return { dir: path.join(root, "발제", "원본"), base };
}

const toSeconds = (s) => {
  const p = s.split(":").map(Number);
  const [h, m, sec] = p.length === 3 ? p : [0, p[0], p[1]];
  return h * 3600 + m * 60 + sec;
};
const pad = (n) => String(n).padStart(2, "0");
const label = (t) => {
  const h = Math.floor(t / 3600),
    m = Math.floor((t % 3600) / 60),
    s = Math.floor(t % 60);
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
};

/**
 * 화자 라벨 처리 — Clips 는 화자 정보가 없고, 회의 녹화(`/rec/`)는 `username` 이 붙는다.
 * 있으면 `이름: 본문` 형태로 살린다.
 */
const cueText = (c) => {
  const t = (c.text || "").replace(/\s+/g, " ").trim();
  return c.username ? `${c.username}: ${t}` : t;
};

function buildVtt(cues) {
  const out = ["WEBVTT", ""];
  cues.forEach((c, i) => {
    out.push(String(i), `${c.startTime} --> ${c.endTime}`, cueText(c), "");
  });
  return out.join("\n");
}

function buildTxt(c) {
  const bits = [];
  if (c.createdTimeIso) {
    // Clips: createdTime 은 업로드 시각이다(세션 시각이 아니다)
    const k = new Date(new Date(c.createdTimeIso).getTime() + 9 * 3600 * 1000);
    bits.push(
      `업로드 ${k.getUTCFullYear()}.${pad(k.getUTCMonth() + 1)}.${pad(k.getUTCDate())} (${WEEKDAYS[k.getUTCDay()]})`,
    );
  } else if (c.fileStartTime) {
    // 회의 녹화: fileStartTime 이 실제 세션 시작이다
    const k = new Date(Number(c.fileStartTime) + 9 * 3600 * 1000);
    bits.push(
      `세션 ${k.getUTCFullYear()}.${pad(k.getUTCMonth() + 1)}.${pad(k.getUTCDate())} (${WEEKDAYS[k.getUTCDay()]}) ${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}`,
    );
  }
  if (c.mediaDuration) bits.push(`${Math.floor(c.mediaDuration / 60)}분 ${c.mediaDuration % 60}초`);
  if (c.ownerName) bits.push(c.ownerName);

  const lines = [c.mediaTopic || `Round${c.round} ${c.kind}`];
  if (bits.length) lines.push(bits.join(" ・ "));
  lines.push("");
  for (const cue of c.transcript) {
    const t = cueText(cue);
    if (t) lines.push(`${label(toSeconds(cue.startTime))}  ${t}`);
  }
  return lines.join("\n") + "\n";
}

function buildMeta(c) {
  return {
    _note: "Zoom Clips 내부 API 원본. chapters·aiSummary 는 Zoom AI 생성물이며 사람이 검수하지 않았다.",
    _chaptersWarning:
      "chapters 의 타임스탬프는 믿지 마라 — R8 검증에서 3건 대조 전부 실제 내용과 어긋났다. 타임라인은 .txt 에서 직접 확인해 만든다.",
    _createdTimeMeaning:
      "클립 업로드 시각이고 세션이 열린 시각이 아니다. 루퍼스 발제는 토요일이고 클립은 다음날 올라오는 경우가 있다.",
    _extractedAt: new Date().toISOString().slice(0, 10),
    round: c.round,
    kind: c.kind,
    mentor: c.mentor,
    shareId: c.shareId,
    shareUrl: c.shareUrl,
    passcodeRequired: true,
    mediaTopic: c.mediaTopic,
    ownerName: c.ownerName,
    mediaDuration: c.mediaDuration,
    durationHuman: label(c.mediaDuration || 0),
    createdTimeIso: c.createdTimeIso,
    plays: c.plays,
    transcriptCueCount: c.transcript.length,
    aiSummary: c.aiSummary,
    chapters: c.chapters,
  };
}

// ── 실행 ──
let raw = JSON.parse(fs.readFileSync(batchPath, "utf8"));
if (typeof raw === "string") raw = JSON.parse(raw);
const results = raw.results.filter((r) => r.ok);

let written = 0;
for (const c of results) {
  const { dir, base } = targetOf(c);
  const files = [
    [path.join(dir, `${base}.vtt`), buildVtt(c.transcript)],
    [path.join(dir, `${base}.txt`), buildTxt(c)],
    [path.join(dir, `${base}_meta.json`), JSON.stringify(buildMeta(c), null, 2) + "\n"],
  ];
  const rel = dir.replace(VAULT + "/", "");
  console.log(`R${c.round} ${c.kind}${c.mentor ? " " + c.mentor : ""} → ${rel}/${base}.{vtt,txt,_meta.json}  (cue ${c.transcript.length})`);
  if (DRY) continue;
  fs.mkdirSync(dir, { recursive: true });
  for (const [p, body] of files) {
    fs.writeFileSync(p, body);
    written++;
  }
}
console.log(`\n${results.length} clip · ${DRY ? "(dry-run)" : written + " 파일 작성"}`);
