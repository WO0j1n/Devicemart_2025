from flask import Flask, request, jsonify
from dotenv import load_dotenv
load_dotenv()

import os
import re
import requests
import urllib.parse
import weaviate
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd

from weaviate.auth import AuthApiKey
from langchain.vectorstores import Weaviate as LangchainWeaviate
from langchain.embeddings import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

app = Flask(__name__)

# 1. Weaviate 클라이언트 생성
def get_weaviate_client():
    return weaviate.Client(
        url=os.environ["WEAVIATE_URL"],
        auth_client_secret=AuthApiKey(api_key=os.environ["WEAVIATE_API_KEY"]),
        additional_headers={"X-OpenAI-Api-Key": os.environ["OPENAI_API_KEY"]}
    )

# 2. Retriever 생성
def get_retriever(class_name="BusinessAPI", top_k=5):
    client = get_weaviate_client()
    vectorstore = LangchainWeaviate(
        client=client,
        index_name=class_name,
        text_key="content",
        embedding=OpenAIEmbeddings(openai_api_key=os.environ["OPENAI_API_KEY"])
    )
    return vectorstore.as_retriever(search_kwargs={"k": top_k})

# 3. Custom Prompt 생성
template = r"""
당신은 유능한 AI 어시스턴트입니다. 아래는 검색된 문서 내용과 질문입니다.

[문서 컨텍스트]
{context}

[질문]
{question}

위 내용을 바탕으로 구체적이고 신뢰도 높은 답변을 작성하세요:
"""
CUSTOM_PROMPT = PromptTemplate(template=template, input_variables=["context", "question"])

# 4. 질문 전처리 함수들
def emphasize_keywords(question: str, keywords: list[str]) -> str:
    for kw in keywords:
        if kw in question:
            question += f" {kw} 관련 정보 {kw} 분석"
    return question

def reformulate_for_search(question: str) -> str:
    base_keywords = re.findall(r"[가-힣]+", question)
    keywords = [kw for kw in base_keywords if len(kw) > 1]
    return " ".join(keywords)

def preprocess_question(question: str) -> str:
    match = re.search(r"([가-힣]+동)", question)
    dong_name = match.group(1) if match else ""

    keywords = ["상권", "입지", "분석", "업종", "추천", "창업", "유동인구", "시간대", "연령대", "혼잡도"]
    emphasized = emphasize_keywords(question, keywords)
    reformatted = reformulate_for_search(emphasized)

    if dong_name:
        return f"""
'{dong_name}' 지역에 대해 유동인구, 업종, 상권, 창업, 시간대 분석과 관련된 문서를 찾고자 합니다.
핵심 키워드: {reformatted}
원 질문: {question}
"""
    return f"{reformatted}\n\n원 질문: {question}"

# ✅ GPT 단독으로 답변할 질문 종류 (필요 시 활용)
gpt_only_types = ["recommendation", "location_analysis"]

# ✅ 응답 후 후처리 (시간대 정리)
def postprocess_response(text):
    return re.sub(r'(\d{2})(\d{2})시', r'\1~\2시', text)

# 5. RAG 수행 함수 (fallback 보장)
def ask_rag(question, retriever=None, fallback_context="", force_gpt=False):
    if force_gpt:
        llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
        response = llm.predict(question)
        return f"\U0001F4A1 GPT 단독 응답\n\n{response}"

    if retriever is None:
        retriever = get_retriever()

    preprocessed = preprocess_question(question)
    try:
        docs = retriever.get_relevant_documents(preprocessed)
    except Exception as e:
        docs = []

    docs = [doc for doc in docs if doc.page_content.strip()]
    is_rag = bool(docs)

    if is_rag:
        context = "\n".join([doc.page_content for doc in docs])
    elif fallback_context.strip():
        context = fallback_context
    else:
        context = ""

    if not context.strip():
        llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
        response = llm.predict(preprocessed)
        return f"\U0001F4A1 GPT 단독 추론 응답 (문서/컨텍스트 없음)\n\n{response}"

    qa_chain = RetrievalQA.from_chain_type(
        llm=ChatOpenAI(model_name="gpt-4", temperature=0.7),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": CUSTOM_PROMPT}
    )

    result = qa_chain({"query": question, "context": context})
    response_text = postprocess_response(result["result"])
    source_type = "\U0001F50D 문서 기반 응답 (RAG)" if is_rag else "\U0001F4A1 GPT 추론 응답 (Fallback Context)"
    return f"{source_type}\n\n{response_text}"

# 6. 유사 업종 수 추정
def get_similar_business_info_rag(gu, dong, business_type):
    query = f"{gu} {dong} {business_type}"
    try:
        headers = {"Authorization": f"KakaoAK {os.environ['KAKAO_REST_API_KEY']}"}
        url = f"https://dapi.kakao.com/v2/local/search/keyword.json?query={urllib.parse.quote(query)}"
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        count = data.get("meta", {}).get("total_count", 0)
        desc = f"카카오 API 기준 '{query}' 관련 업종 수는 약 {count}건으로 확인됩니다."
        return {"description": desc, "count": count}
    except Exception as e:
        return {"description": f"카카오 API 호출 오류: {e}", "count": 0}

# 7. 유망 업종 추천 (GPT 강제)
def get_rag_business_recommendation(gu, dong, population, estate_data):
    pop = population.get("PSNG_NO", "정보 없음") if population else "정보 없음"
    deals = len(estate_data) if estate_data else 0

    fallback_context = f"""
'{gu} {dong}' 지역은 상업 및 주거 기능이 복합된 지역으로 파악됩니다. 해당 지역의 유동인구는 약 {pop}명이며,
최근 부동산 거래는 {deals}건 발생했습니다. 유동인구가 꾸준하고 상업 활동이 활발한 지역에서는 카페, 음식점, 편의점, 미용실 등
생활 밀착형 업종이 안정적으로 운영될 가능성이 높습니다.

또한 경쟁 업체 수, 임대료 수준, 상권 접근성, 고객 선호도 등의 요소를 종합적으로 고려하여 업종을 선택하는 것이 중요합니다.
"""

    question = f"{gu} {dong} 지역의 상권 데이터를 바탕으로 유망한 창업 업종을 추천하고, 그 이유를 구체적으로 설명해주세요."
    return ask_rag(question, fallback_context=fallback_context, force_gpt=True)

# 8. 입지 분석 (GPT 강제)
def get_location_analysis_with_rag(gu, dong, item, population, estate_data, similar_desc):
    pop = population.get("PSNG_NO", "정보 없음") if population else "정보 없음"
    deals = len(estate_data) if estate_data else 0

    fallback_context = f"""
서울시 {gu} {dong} 지역에서 '{item}' 업종의 입지 분석을 요청하였습니다.
- 유동인구: {pop}명
- 부동산 거래 건수: {deals}건
- 유사 업종 정보: {similar_desc}

이 정보를 바탕으로 '{item}' 업종이 이 지역에서 창업하기에 적합한지 구체적으로 평가해주세요.
"""

    question = f"{gu} {dong} 지역에서 '{item}' 업종의 창업 가능성을 분석해주세요."
    return ask_rag(question, fallback_context=fallback_context, force_gpt=True)

# 9. 자유 질의 (RAG)
def ask_chat_with_rag(user_input, analyzed_context):
    context = ""

    if analyzed_context:
        population = analyzed_context.get("population") or {}
        similar = analyzed_context.get("similar") or {}

        context = f"""
[분석 요약]
- 지역: {analyzed_context.get('gu', '')} {analyzed_context.get('dong', '')}
- 업종: {analyzed_context.get('item', '')}
- 유동인구: {population.get('PSNG_NO', '정보 없음')}
- 유사 업종: {similar.get('description', '정보 없음')}
- 창업 평가: {analyzed_context.get('score', '정보 없음')}
- 추천 업종: {analyzed_context.get('recommendation', '정보 없음')}
- 입지 분석: {analyzed_context.get('location_analysis', '정보 없음')}
"""
    return ask_rag(context + "\n\n" + user_input)

# 부동산 거래 데이터 조회 관련 설정 및 함수
REAL_ESTATE_API = "http://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
REAL_ESTATE_KEY = os.environ["REAL_ESTATE_KEY"]
POPULATION_API_KEY = os.environ["POPULATION_API_KEY"]
POPULATION_API = f"http://openapi.seoul.go.kr:8088/{POPULATION_API_KEY}/json/tpssPassengerCnt/1/1000"

# 지역 코드 매핑 로드
with open("real_estate.json", "r", encoding="utf-8") as f:
    gu_code_map = json.load(f)

# 주소 마스터 데이터 로드
with open("address_master.json", "r", encoding="utf-8") as f:
    address_data = json.load(f)

def get_real_estate_by_dong(gu, dong):
    lawd_cd = gu_code_map.get(gu)
    if not lawd_cd:
        return []
    now = datetime.now()
    results = []
    for i in range(6):
        yyyymm = (now.replace(day=1) - pd.DateOffset(months=i)).strftime("%Y%m")
        params = {
            "serviceKey": REAL_ESTATE_KEY,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": yyyymm,
            "pageNo": "1",
            "numOfRows": "100",
            "type": "xml"
        }
        try:
            res = requests.get(REAL_ESTATE_API, params=params, timeout=10)
            root = ET.fromstring(res.content)
            items = root.find("body/items")
            if items is not None:
                for item in items.findall("item"):
                    umd = item.findtext("umdNm", default="N/A")
                    if dong in umd:
                        results.append({
                            "dealAmount": item.findtext("dealAmount", "N/A"),
                            "dealYear": int(item.findtext("dealYear", "0")),
                            "dealMonth": int(item.findtext("dealMonth", "0")),
                            "dealDay": int(item.findtext("dealDay", "0")),
                            "buildingType": item.findtext("buildingType", "N/A")
                        })
        except Exception as e:
            print("[ERROR] 부동산 API 오류:", e)
            continue
    results.sort(key=lambda x: (x["dealYear"], x["dealMonth"], x["dealDay"]), reverse=True)
    return results[:30]

def get_passenger_info_by_dong(gu, dong):
    target_id = None
    for entry in address_data["DATA"]:
        if entry["cgg_nm"] == gu and entry["dong_nm"] == dong and len(entry.get("dong_id", "")) == 8:
            target_id = entry["dong_id"]
            break

    if not target_id:
        return None

    try:
        res = requests.get(POPULATION_API, timeout=10)
        if res.status_code == 200:
            data = res.json()
            rows = data.get("tpssPassengerCnt", {}).get("row", [])
            for row in rows:
                if row.get("DONG_ID") == target_id:
                    return row
    except Exception as e:
        print("[ERROR] 유동인구 API 오류:", e)
    return None

def evaluate_suitability(pop, estate_data, similar_count):
    score = 0
    try:
        total = int(pop.get("RIDE_PASGR_NUM", 0)) + int(pop.get("ALIGHT_PASGR_NUM", 0)) if pop else 0
        if total > 5000:
            score += 1
    except:
        pass
    try:
        if estate_data:
            recent = [int(x["dealAmount"].replace(",", "")) for x in estate_data if x["dealAmount"] != "N/A"]
            if recent and sum(recent)/len(recent) < 120000:
                score += 1
    except:
        pass
    if similar_count < 10:
        score += 1
    if score == 3:
        return "✅ 매우 적합한 입지예요! 👍"
    elif score == 2:
        return "⚠️ 나쁘지는 않지만 경쟁을 고려하세요."
    else:
        return "❌ 다소 불리한 입지입니다."

def analyze_market(gu, dong, item, get_similar_business_info_rag, get_rag_business_recommendation, get_location_analysis_with_rag):
    estate = get_real_estate_by_dong(gu, dong)
    pop = get_passenger_info_by_dong(gu, dong)
    similar = get_similar_business_info_rag(gu, dong, item)
    score = evaluate_suitability(pop, estate, similar["count"])
    recommendation = get_rag_business_recommendation(gu, dong, pop, estate)
    location_analysis = get_location_analysis_with_rag(gu, dong, item, pop, estate, similar["description"])

    return {
        "gu": gu,
        "dong": dong,
        "item": item,
        "population": pop,
        "estate": estate,
        "similar": similar,
        "score": score,
        "recommendation": recommendation,
        "location_analysis": location_analysis
    }

# ===== Flask API 엔드포인트 =====

@app.route('/ask_rag', methods=['POST'])
def ask_rag_endpoint():
    data = request.get_json()
    question = data.get('question', '')
    force_gpt = data.get('force_gpt', False)
    response = ask_rag(question, force_gpt=force_gpt)
    return jsonify({"response": response})

@app.route('/similar_business_info', methods=['GET'])
def similar_business_info_endpoint():
    gu = request.args.get('gu')
    dong = request.args.get('dong')
    business_type = request.args.get('business_type')
    if not all([gu, dong, business_type]):
        return jsonify({"error": "gu, dong, and business_type parameters are required."}), 400
    response = get_similar_business_info_rag(gu, dong, business_type)
    return jsonify(response)

@app.route('/recommend_business', methods=['GET'])
def recommend_business_endpoint():
    gu = request.args.get('gu')
    dong = request.args.get('dong')
    if not all([gu, dong]):
        return jsonify({"error": "gu and dong parameters are required."}), 400
    pop = get_passenger_info_by_dong(gu, dong)
    estate = get_real_estate_by_dong(gu, dong)
    response = get_rag_business_recommendation(gu, dong, pop, estate)
    return jsonify({"recommendation": response})

@app.route('/location_analysis', methods=['GET'])
def location_analysis_endpoint():
    gu = request.args.get('gu')
    dong = request.args.get('dong')
    item = request.args.get('item')
    if not all([gu, dong, item]):
        return jsonify({"error": "gu, dong, and item parameters are required."}), 400
    pop = get_passenger_info_by_dong(gu, dong)
    estate = get_real_estate_by_dong(gu, dong)
    similar = get_similar_business_info_rag(gu, dong, item)
    response = get_location_analysis_with_rag(gu, dong, item, pop, estate, similar["description"])
    return jsonify({"location_analysis": response})

@app.route('/analyze_market', methods=['GET'])
def analyze_market_endpoint():
    gu = request.args.get('gu')
    dong = request.args.get('dong')
    item = request.args.get('item')
    if not all([gu, dong, item]):
        return jsonify({"error": "gu, dong, and item parameters are required."}), 400
    result = analyze_market(gu, dong, item, get_similar_business_info_rag, get_rag_business_recommendation, get_location_analysis_with_rag)
    return jsonify(result)

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
