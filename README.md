# 📘 창업 분석 Flask API 명세서 + React 연동 가이드

## ✅ 공통 사항
- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json`
- **지원 포맷**: JSON
- **CORS 허용**: O (Flask + flask-cors 설정 완료)

---

## 🔍 1. 창업 지역/업종 분석 API

### 📥 Endpoint
`POST /analyze`

### 📝 설명
입력받은 자치구, 행정동, 업종 정보를 기반으로:
- 유사 업종 수 조회
- 창업 적합도 평가
- GPT 기반 창업 업종 추천
- GPT 기반 입지 분석 수행

### 📤 Request Body 예시
```json
{
  "gu": "용산구",
  "dong": "한남동",
  "item": "카페",
  "population": {
    "PSNG_NO": 8500
  },
  "estate": [
    {
      "dealAmount": "110,000",
      "dealYear": 2024,
      "dealMonth": 12,
      "dealDay": 10,
      "buildingType": "오피스텔"
    }
  ]
}
```

### ✅ 필드 설명
| 필드 | 설명 | 필수 |
|------|------|------|
| `gu` | 자치구명 (예: 강남구) | ✅ |
| `dong` | 행정동명 (예: 역삼동) | ✅ |
| `item` | 업종명 (예: 카페, 편의점) | ✅ |
| `population.PSNG_NO` | 유동인구 수 | ⭕ (없으면 GPT 분석 정확도 낮아짐) |
| `estate` | 최근 부동산 거래 내역 리스트 | ⭕ (없으면 분석 시 GPT에게 빈값 전달) |

### 📥 Response 예시
```json
{
  "score": "✅ 매우 적합한 입지예요! 👍",
  "recommendation": "디저트 카페, 베이커리 추천. 유동인구가 높고 경쟁이 적당합니다.",
  "location_analysis": "주거지와 상업지가 혼합된 지역이며 유동인구가 풍부하여 입지 적합성이 높습니다.",
  "similar": {
    "description": "카카오 API 기준 '용산구 한남동 카페' 관련 업종 수는 약 8건으로 확인됩니다.",
    "count": 8
  }
}
```

---

## 💬 2. 자유 질의 GPT 응답 API (챗봇)

### 📥 Endpoint
`POST /ask`

### 📝 설명
사용자가 자유롭게 입력한 질문에 대해:
- RAG 기반 GPT 응답
- 또는 fallback GPT 추론 응답 제공

### 📤 Request 예시 (with context)
```json
{
  "question": "한남동에 디저트 카페 창업 어때?",
  "analyzed": {
    "gu": "용산구",
    "dong": "한남동",
    "item": "카페",
    "population": { "PSNG_NO": 8500 },
    "similar": { "description": "카카오 기준 8건" },
    "score": "적합",
    "recommendation": "디저트 카페",
    "location_analysis": "유동인구가 많고, 주거지와 인접"
  }
}
```

### 📤 Response 예시
```json
{
  "answer": "🔍 문서 기반 응답 (RAG)\n\n한남동은 유동인구가 풍부하고 경쟁이 적절한 지역으로 디저트 카페 입지로 적합합니다."
}
```

---

## ⚛️ React 연동 가이드 예시

```tsx
// GPT 자유 질문 예시 (POST /ask)
async function askGPT() {
  const res = await fetch("http://localhost:8000/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: "한남동 디저트 카페 잘 될까?",
      analyzed: { gu: "용산구", dong: "한남동", item: "카페" }
    })
  });
  const data = await res.json();
  console.log("답변:", data.answer);
}

// 지역 분석 예시 (POST /analyze)
async function analyzeArea() {
  const res = await fetch("http://localhost:8000/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      gu: "용산구",
      dong: "한남동",
      item: "카페",
      population: { PSNG_NO: 8500 },
      estate: []
    })
  });
  const data = await res.json();
  console.log("창업 적합도:", data.score);
  console.log("추천 업종:", data.recommendation);
  console.log("입지 분석:", data.location_analysis);
}
```

---

## 📦 .env 예시 (백엔드용)
```env
OPENAI_API_KEY=sk-xxxx
WEAVIATE_URL=http://localhost:8080
WEAVIATE_API_KEY=your_weaviate_key
KAKAO_REST_API_KEY=your_kakao_key
REAL_ESTATE_KEY=your_real_estate_key
POPULATION_API_KEY=your_population_key
```

---

이 가이드를 React 개발자에게 전달하면 바로 연동 가능해! 필요한 경우 Swagger 문서 형태로도 변환 가능 👍

