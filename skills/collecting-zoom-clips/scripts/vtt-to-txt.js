#!/usr/bin/env node
/**
 * Zoom Clips VTT → 볼트 평문 녹취록(.txt)
 *
 * 사용:
 *   node vtt-to-txt.js <input.vtt> [meta.json] > out.txt
 *
 * meta.json(선택)이 있으면 헤더를 채운다 — Round8_발제_meta.json 형태:
 *   { mediaTopic, ownerName, mediaDuration, createdTimeIso }
 *
 * 출력 형태 (기존 볼트 녹취록 관례에 맞춤):
 *   Loop:Pak FE Vol.1 - Round8 발제
 *   업로드 2026.08.09 (일) ・ 69분 2초 ・ 헬퍼 루퍼스
 *
 * ⚠️ createdTime은 **클립 업로드 시각**이고 세션이 열린 시각이 아니다.
 *    루퍼스 발제는 토요일인데 클립은 다음날 올라오는 경우가 있다
 *    (R8: 세션 추정 08.08 토 / 업로드 08.09 일). 그래서 "업로드"를 명시한다.
 *
 *   00:04  아 아 네 안녕하세요 들리시나요?
 *   00:13  네네네 반갑습니다...
 *
 * 화자 라벨은 넣지 않는다 — Clips API 응답에 화자 정보가 없다.
 * (기존 R2 .txt의 `참석자 N`은 회의 녹화 transcript 산출물이라 출처가 다르다.)
 */

const fs = require("node:fs");

const [vttPath, metaPath] = process.argv.slice(2);
if (!vttPath) {
  console.error("usage: node vtt-to-txt.js <input.vtt> [meta.json]");
  process.exit(1);
}

/** "00:01:09.020" → 초 */
function toSeconds(stamp) {
  const parts = stamp.split(":").map(Number);
  const [h, m, s] = parts.length === 3 ? parts : [0, parts[0], parts[1]];
  return h * 3600 + m * 60 + s;
}

/** 초 → "MM:SS" (1시간 넘으면 "H:MM:SS") */
function toLabel(total) {
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = Math.floor(total % 60);
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function buildHeader(meta) {
  if (!meta) return null;
  const lines = [];
  if (meta.mediaTopic) lines.push(meta.mediaTopic);

  const bits = [];
  if (meta.createdTimeIso) {
    // KST 기준으로 표기 (강의는 한국 시간대에서 열린다)
    const kst = new Date(new Date(meta.createdTimeIso).getTime() + 9 * 3600 * 1000);
    const y = kst.getUTCFullYear();
    const mo = String(kst.getUTCMonth() + 1).padStart(2, "0");
    const d = String(kst.getUTCDate()).padStart(2, "0");
    bits.push(`업로드 ${y}.${mo}.${d} (${WEEKDAYS[kst.getUTCDay()]})`);
  }
  if (meta.mediaDuration) {
    const m = Math.floor(meta.mediaDuration / 60);
    const s = meta.mediaDuration % 60;
    bits.push(`${m}분 ${s}초`);
  }
  if (meta.ownerName) bits.push(meta.ownerName);
  if (bits.length) lines.push(bits.join(" ・ "));

  return lines.length ? lines.join("\n") : null;
}

// ── VTT 파싱 ──
// 블록 구분은 빈 줄. 각 블록: [번호] / "start --> end" / 본문 1~N줄
const raw = fs.readFileSync(vttPath, "utf8").replace(/^﻿/, "");
const blocks = raw.split(/\r?\n\r?\n/);

const cues = [];
for (const block of blocks) {
  const lines = block.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (!lines.length || lines[0].startsWith("WEBVTT")) continue;

  const arrowIdx = lines.findIndex((l) => l.includes("-->"));
  if (arrowIdx === -1) continue;

  const start = lines[arrowIdx].split("-->")[0].trim();
  const text = lines
    .slice(arrowIdx + 1)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  if (text) cues.push({ label: toLabel(toSeconds(start)), text });
}

const meta = metaPath ? JSON.parse(fs.readFileSync(metaPath, "utf8")) : null;
const header = buildHeader(meta);

const out = [];
if (header) out.push(header, "");
for (const c of cues) out.push(`${c.label}  ${c.text}`);

process.stdout.write(out.join("\n") + "\n");
process.stderr.write(`cue ${cues.length}개 변환\n`);
