# 📘 창업 분석 Flask API 명세서 + React 연동 가이드

## ✅ 공통 사항
- **Base URL**: `http://localhost:8080`
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

| 필드                   | 설명                                  | 필수                          |
|----------------------|-------------------------------------|-----------------------------|
| `gu`                 | 자치구명 (예: 강남구)                    | ✅                         |
| `dong`               | 행정동명 (예: 역삼동)                    | ✅                         |
| `item`               | 업종명 (예: 카페, 편의점)                 | ✅                         |
| `population.PSNG_NO` | 유동인구 수                             | ⭕ (없으면 GPT 분석 정확도 낮아짐) |
| `estate`             | 최근 부동산 거래 내역 리스트                | ⭕ (없으면 분석 시 GPT에게 빈값 전달) |

### 📤 Response 예시
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

아래는 지금까지 작성한 코드와 기능을 기반으로 한 API 명세서 예시입니다.

---

# Flask Business Analysis API 명세서

**Base URL:**  
- 개발 환경: `http://127.0.0.1:8080`  
- (실제 배포 환경에 따라 변경)

> **참고:** API는 환경 변수와 외부 JSON 파일(`real_estate.json`, `address_master.json`)을 사용합니다.  
> 환경 변수 설정은 `.env` 파일에 다음과 같이 포함되어야 합니다:  
> - `WEAVIATE_URL`  
> - `WEAVIATE_API_KEY`  
> - `OPENAI_API_KEY`  
> - `KAKAO_REST_API_KEY`  
> - `REAL_ESTATE_KEY`  
> - `POPULATION_API_KEY`

---

## 1. Health Check

### **Endpoint:** `/ping`  
- **Method:** GET  
- **URL:**  
  ```
  http://127.0.0.1:8080/ping
  ```
- **설명:**  
  서버가 정상적으로 실행 중인지 확인하기 위한 간단한 헬스 체크 엔드포인트입니다.
- **성공 응답 (200 OK):**
  ```json
  {
    "message": "pong"
  }
  ```

---

## 2. 질문 기반 문서/챗봇 응답 (RAG)

### **Endpoint:** `/ask_rag`  
- **Method:** POST  
- **URL:**  
  ```
  http://127.0.0.1:8080/ask_rag
  ```
- **요청 헤더:**  
  - `Content-Type: application/json`
- **요청 본문 (JSON):**
  ```json
  {
    "question": "강남역 주변 상권 분석 부탁해",
    "force_gpt": false
  }
  ```
- **설명:**  
  입력된 질문을 전처리한 후, RAG 체인을 사용해 관련 문서를 검색하고 GPT-4를 활용하여 답변을 생성합니다.  
  - **force_gpt:** `true`인 경우, 문서 검색 없이 GPT 단독으로 답변합니다.
- **성공 응답 (200 OK):**  
  - 관련 문서가 조회된 경우:
    ```json
    {
      "response": "🪢 문서 기반 응답 (RAG)\n\n[RAG 체인에 의한 답변 내용...]"
    }
    ```
  - 관련 문서가 없거나 오류가 발생하면:
    ```json
    {
      "response": "🪄 GPT 단독 추론 응답 (문서/컨텍스트 없음)\n\n[GPT 추론 응답 내용...]"
    }
    ```

---

## 3. 유사 업종 수 조회

### **Endpoint:** `/similar_business_info`  
- **Method:** GET  
- **URL:**  
  ```
  http://127.0.0.1:8080/similar_business_info
  ```
- **Query Parameters:**
  - `gu` (필수): 구 이름 (예: "강남구")
  - `dong` (필수): 동 이름 (예: "역삼동")
  - `business_type` (필수): 업종 (예: "카페")
- **설명:**  
  카카오 API를 호출하여 지정된 구/동 및 업종과 관련된 건수를 반환합니다.
- **성공 응답 (200 OK):**
  ```json
  {
    "description": "카카오 API 기준 '강남구 역삼동 카페' 관련 업종 수는 약 123건으로 확인됩니다.",
    "count": 123
  }
  ```
- **오류 응답 (400 Bad Request):**
  ```json
  {
    "error": "gu, dong, and business_type parameters are required."
  }
  ```

---

## 4. 유망 업종 추천

### **Endpoint:** `/recommend_business`  
- **Method:** GET  
- **URL:**  
  ```
  http://127.0.0.1:8080/recommend_business
  ```
- **Query Parameters:**
  - `gu` (필수): 구 이름 (예: "강남구")
  - `dong` (필수): 동 이름 (예: "역삼동")
- **설명:**  
  해당 지역의 유동인구, 부동산 거래 데이터 등을 바탕으로 GPT를 사용해 유망한 창업 업종과 그 이유를 추천합니다.
- **성공 응답 (200 OK):**
  ```json
  {
    "recommendation": "🪄 GPT 단독 응답\n\n[추천 내용: ...]"
  }
  ```
- **오류 응답 (400 Bad Request):**
  ```json
  {
    "error": "gu and dong parameters are required."
  }
  ```

---

## 5. 입지 분석

### **Endpoint:** `/location_analysis`  
- **Method:** GET  
- **URL:**  
  ```
  http://127.0.0.1:8080/location_analysis
  ```
- **Query Parameters:**
  - `gu` (필수): 구 이름 (예: "강남구")
  - `dong` (필수): 동 이름 (예: "역삼동")
  - `item` (필수): 분석 대상 업종 (예: "음식점")
- **설명:**  
  지정된 구/동과 업종에 대해 유동인구, 부동산 거래 건수, 유사 업종 정보를 활용하여 입지 분석을 진행합니다.
- **성공 응답 (200 OK):**
  ```json
  {
    "location_analysis": "🪄 GPT 단독 응답\n\n[입지 분석 결과: ...]"
  }
  ```
- **오류 응답 (400 Bad Request):**
  ```json
  {
    "error": "gu, dong, and item parameters are required."
  }
  ```

---

## 6. 전체 시장 분석

### **Endpoint:** `/analyze_market`  
- **Method:** GET  
- **URL:**  
  ```
  http://127.0.0.1:8080/analyze_market
  ```
- **Query Parameters:**
  - `gu` (필수): 구 이름 (예: "강남구")
  - `dong` (필수): 동 이름 (예: "역삼동")
  - `item` (필수): 분석 대상 업종 (예: "음식점")
- **설명:**  
  해당 지역의 부동산 거래 데이터, 유동인구 정보, 유사 업종 정보 등을 종합하여 시장 전체를 분석합니다.  
  분석 결과에는 평가 점수, 추천 업종, 입지 분석 결과 등이 포함됩니다.
- **성공 응답 (200 OK):**
  ```json
  {
    "gu": "강남구",
    "dong": "역삼동",
    "item": "음식점",
    "population": { /* 유동인구 데이터 */ },
    "estate": [ /* 부동산 거래 데이터 */ ],
    "similar": {
      "description": "카카오 API 기준 '강남구 역삼동 음식점' 관련 업종 수는 약 10건으로 확인됩니다.",
      "count": 10
    },
    "score": "✅ 매우 적합한 입지예요! 👍",
    "recommendation": "[추천 내용]",
    "location_analysis": "[입지 분석 내용]"
  }
  ```
- **오류 응답 (400 Bad Request):**
  ```json
  {
    "error": "gu, dong, and item parameters are required."
  }
  ```

---

## 7. 챗봇 대화 (RAG 기반 응답)

### **대화 방식 및 설명:**
- 챗봇과 자유로운 대화를 위한 함수 `ask_chat_with_rag`는 사용자 입력과 사전 분석된 컨텍스트를 조합하여 `ask_rag`를 호출합니다.
- **RAG (Retrieval Augmented Generation) 방식:**  
  - 질문 전처리 후, 관련 문서를 **retriever**로 검색합니다.
  - 검색된 문서들을 컨텍스트로 하여 GPT-4가 답변을 생성합니다.
  - 따라서, 챗봇 응답은 단순 GPT 추론이 아니라, **문서 기반 응답(RAG)**으로 동작합니다.

> **참고:** `/ask_rag` 엔드포인트는 챗봇 대화에서도 동일하게 사용됩니다.  
> 사용자가 질문을 보내면 RAG 체인이 작동하여 관련 문서와 함께 신뢰도 높은 답변을 생성합니다.

---

# 사용 예시

### 1. `/ask_rag` POST 요청 (Postman)
- **URL:** `http://127.0.0.1:8080/ask_rag`
- **Headers:**  
  - Content-Type: `application/json`
- **Body (raw JSON):**
  ```json
  {
    "question": "강남역 주변 상권 분석 부탁해",
    "force_gpt": false
  }
  ```
- **예상 응답:**
  ```json
  {
    "response": "🪢 문서 기반 응답 (RAG)\n\n[RAG 체인에 의한 답변 내용...]"
  }
  ```

---

# 추가 참고 사항

- **환경 설정:**  
  API 동작을 위해 필요한 환경 변수 및 외부 JSON 파일이 올바르게 설정되어 있어야 합니다.
- **오류 처리:**  
  필수 파라미터가 누락되면 400 에러와 함께 적절한 오류 메시지를 반환합니다.
- **RAG 방식:**  
  `/ask_rag` 및 챗봇 관련 기능은 RAG 체인을 사용하여 문서 검색과 GPT 추론을 결합합니다.

---
