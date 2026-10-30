# 기름값 신호등 — 데이터 수집

토스 미니앱 '기름값 신호등'이 읽는 데이터를 자동으로 만드는 저장소예요.

```
오피넷(한국석유공사) → GitHub Actions가 하루 6번 자동 수집 → docs/data/*.json → 미니앱
```

## 자동 실행 시각 (한국시간)

| 시각 | 하는 일 | 오피넷 호출 |
|---|---|---|
| 매일 00:40 | 전체 수집: 일평균 확정치, 시도·시군구 평균, 최저가 주유소 | 약 200회 |
| 09:10 · 12:10 · 16:10 · 19:10 | 현재 전국·시도 평균만 갱신 | 2회씩 |
| 금요일 10:25 | 주간 평균 | 3회 |

오피넷 일반 API는 하루 300회까지라서, 280회를 넘지 않게 `state/state.json`에 날짜별 호출 수를 기록하고 넘으면 멈춰요.

## 사람이 고치는 파일: `config/events.json`

- **유류세**: 정부 발표가 나오면 `tax_cut.status`를 바꿔요.
  - `pending` 연장 여부 미정 / `extended` 연장됨(`extended_to`에 날짜) / `ending` 종료 확정
  - 종료 확정이면 신호가 무조건 빨강이 돼요.
- **석유공사 다음 주 전망**: 매주 토요일 발표를 보고 `outlook`에 적어요.
  - `direction`: `up` / `down` / `flat`, `published`: 발표일(예 `2026-10-31`)
  - 8일이 지나면 자동으로 무시돼요.

## 신호 규칙 요약 (`scripts/signal_rules.py`)

점수를 더해 3점 이상이면 빨강(이번 주 안에 넣으세요), -3점 이하면 초록(서두르지 않아도 돼요), 그 사이는 노랑.

- 최근 3일 확정 일평균: 3일 이상 연속 4원 이상 오르면 +3, 2일 연속 3원 이상 +2, 1원 이상 +1 (내림은 반대)
- 주간 평균이 전주보다 5원 이상 오르면 +1 (내리면 -1)
- 석유공사 다음 주 전망: 상승 +2 / 하락 -2
- 유류세 종료 확정 → 무조건 빨강, 미정인데 14일 이내 → 초록 금지

## 공개 파일

- `docs/data/latest.json` 전국 평균, 신호, 30일 추세, 유류세 카드, 시도 평균
- `docs/data/regions.json` 시도·시군구 목록
- `docs/data/region/<시도코드>.json` 시군구 평균, 시도 최저가 TOP10, 수도권은 시군구별 최저가 TOP5
- `docs/data/push.json` 신호가 바뀌었을 때 보낼 알림 문구 제안

자료 출처: 한국석유공사 오피넷

## 점검

```bash
bash tests/run_scenarios.sh /tmp/gas-test   # 샘플 응답으로 7가지 상황 점검 (오피넷 호출 없음)
```

## 토스 미니앱 (`app/`)

- 화면 코드: `app/src/` (view.js 화면 조각, main.js 동작, sdk.js 토스 SDK 연결, config.js 운영 설정)
- `app/**`를 고쳐 올리면 GitHub Actions가 자동으로 빌드해서 `release/gas-signal.ait`와 `release/build-log.txt`를 저장해요.
- 콘솔 '앱 출시'에서 `release/gas-signal.ait`를 올리면 돼요. 영문 앱 이름은 `gas-signal` (apps-in-toss.config.ts와 같아야 함).
- 광고·알림은 `app/src/config.js`에 콘솔에서 받은 ID를 넣으면 켜져요. 비워두면 꺼진 상태로 동작해요.
- 미리보기: `python3 tests/build_preview.py 미리보기.html 02 0236`
