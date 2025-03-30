from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os

# RAG 로직 불러오기
from rag_utils_flask import (
    get_similar_business_info_rag,
    get_rag_business_recommendation,
    get_location_analysis_with_rag,
    ask_chat_with_rag
)

# .env 파일 불러오기
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)  # CORS 허용 (React 연동 시 필수)

# 👉 /ask: 자유 질의 GPT
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question", "")
    analyzed = data.get("analyzed", {})  # 추가된 분석 context (선택)

    print("🧾 받은 질문:", question)

    if not question:
        return jsonify({"error": "질문이 비어 있습니다."}), 400

    try:
        answer = ask_chat_with_rag(question, analyzed_context=analyzed)
        return jsonify({"answer": answer})
    except Exception as e:
        print("❌ 오류:", e)
        return jsonify({"error": str(e)}), 500

# 👉 /analyze: 지역 및 업종 분석
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    gu = data.get("gu")
    dong = data.get("dong")
    item = data.get("item")
    population = data.get("population", {})
    estate = data.get("estate", [])

    if not gu or not dong or not item:
        return jsonify({"error": "필수 입력 값(gu, dong, item)이 부족합니다."}), 400

    try:
        similar = get_similar_business_info_rag(gu, dong, item)
        score = "🔍 평가 로직은 이곳에 구현"
        recommendation = get_rag_business_recommendation(gu, dong, population, estate)
        location_analysis = get_location_analysis_with_rag(gu, dong, item, population, estate, similar["description"])

        return jsonify({
            "score": score,
            "recommendation": recommendation,
            "location_analysis": location_analysis,
            "similar": similar
        })
    except Exception as e:
        print("❌ 분석 오류:", e)
        return jsonify({"error": str(e)}), 500

# ✅ 서버 실행
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
