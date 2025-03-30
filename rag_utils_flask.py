from dotenv import load_dotenv
load_dotenv()

import os
import requests
import urllib.parse
import weaviate
from weaviate.auth import AuthApiKey

from langchain_community.vectorstores import Weaviate as LangchainWeaviate
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

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

# 3. Custom Prompt
template = """
당신은 유능한 AI 어시스턴트입니다. 아래는 검색된 문서 내용과 질문입니다.

[문서 컨텍스트]
{context}

[질문]
{question}

위 내용을 바탕으로 구체적이고 신뢰도 높은 답변을 작성하세요:
"""
CUSTOM_PROMPT = PromptTemplate(template=template, input_variables=["context", "question"])

# 4. RAG 질의 함수
def ask_rag(question, retriever=None, fallback_context=""):
    if retriever is None:
        retriever = get_retriever()

    docs = retriever.get_relevant_documents(question)
    is_rag = False

    if docs:
        context = "\n".join([doc.page_content for doc in docs])
        is_rag = True
    elif fallback_context.strip():
        context = fallback_context
    else:
        llm = ChatOpenAI(model_name="gpt-4", temperature=0.3)
        response = llm.predict(question)
        return f"\ud83d\udca1 GPT 단독 추론 응답 (문서 없음)\n\n{response}"

    qa_chain = RetrievalQA.from_chain_type(
        llm=ChatOpenAI(model_name="gpt-4", temperature=0.3),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": CUSTOM_PROMPT}
    )

    result = qa_chain.invoke({"query": question, "context": context})
    response_text = result["result"]
    source_type = "\ud83d\udd0d 문서 기반 응답 (RAG)" if is_rag else "\ud83d\udca1 GPT 추론 응답 (Fallback Context)"

    return f"{source_type}\n\n{response_text}"

# 5. 유사 업종 수 추정 (카카오 API)
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

# 6. 창업 업종 추천 (RAG + fallback context)
def get_rag_business_recommendation(gu, dong, population, estate_data):
    pop = population.get("PSNG_NO", "정보 없음") if population else "정보 없음"
    deals = len(estate_data) if estate_data else 0
    retriever = get_retriever()

    fallback_context = f"""
{gu} {dong} 지역은 상업 지구와 주거 지구가 혼합된 곳으로 유동인구는 약 {pop}명이며,
최근 부동산 거래는 {deals}건 발생했습니다. 일반적으로 카페, 음식점, 편의점, 생활 밀착 업종이 창업 업종으로 고려됩니다.
"""

    question = f"{gu} {dong} 지역의 상권 데이터를 바탕으로 유망한 창업 업종을 추천하고, 그 이유를 구체적으로 설명해주세요."
    return ask_rag(question, retriever=retriever, fallback_context=fallback_context)

# 7. 입지 분석 (RAG 기반 분석)
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
    return ask_rag(question, fallback_context=fallback_context)

# 8. 자유 질의 GPT (Flask 전용)
def ask_chat_with_rag(user_input, analyzed_context=None):
    context = ""

    if analyzed_context:
        context = f"""
[분석 요약]
- 지역: {analyzed_context.get('gu')} {analyzed_context.get('dong')}
- 업종: {analyzed_context.get('item')}
- 유동인구: {analyzed_context.get('population', {}).get('PSNG_NO', '정보 없음')}
- 유사 업종: {analyzed_context.get('similar', {}).get('description', '없음')}
- 창업 평가: {analyzed_context.get('score')}
- 추천 업종: {analyzed_context.get('recommendation')}
- 입지 분석: {analyzed_context.get('location_analysis')}
"""

    return ask_rag(context + "\n\n" + user_input)
