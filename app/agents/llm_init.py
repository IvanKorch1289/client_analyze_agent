from langchain_huggingface import HuggingFaceEndpoint

from app.settings import settings

llm = HuggingFaceEndpoint(
    repo_id=settings.huging_face_model,
    huggingfacehub_api_token=settings.hugging_face_token,
    temperature=settings.temperature,
    task="text-generation",
    max_new_tokens=settings.max_new_tokens,
    do_sample=settings.do_sample,
    # Опционально: добавляем параметры для стабильности
    top_k=50,
    top_p=0.95,
    repetition_penalty=1.2,
)
