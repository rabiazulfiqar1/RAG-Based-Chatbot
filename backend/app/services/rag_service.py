"""
RAG (Retrieval-Augmented Generation) service for document Q&A.
"""

from typing import List
from langgraph.graph import StateGraph, START
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.models.schemas import RAGState
from app.core.connections import document_vector_store, llm


# RAG Prompt Template
rag_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful AI assistant that answers questions based on provided documents.
    
    Instructions:
    - Use ONLY the provided context to answer questions
    - If the answer is not in the context, say "I cannot find that information in the uploaded documents"
    - Be specific and cite relevant parts when possible
    - If asked about multiple documents, clarify which document contains what information
    """),
    ("user", """Context from documents:{context}
    Question: {question}
    Please provide a detailed answer based on the context above.""")
])

# RAG Chain
rag_chain = rag_prompt | llm | StrOutputParser()


def retrieve_documents(state: RAGState):
    """Retrieve relevant documents from vector store"""
    session_id = state.session_id
    question = state.question
    document_ids = state.document_ids or []
    
    # Build filter
    if len(document_ids) > 1:
        all_docs = []

        for doc_id in state.document_ids:
            docs = document_vector_store.similarity_search(
                state.question,
                k=4,
                filter={
                    "session_id": state.session_id,
                    "document_id": doc_id
                }
            )
            all_docs.extend(docs)

        return {"context": all_docs}

    filter_dict = {"session_id": session_id}
    if document_ids:
        filter_dict["document_id"] = {"$in": document_ids}
    
    try:
        retrieved_docs = document_vector_store.similarity_search(
            question,
            k=8,  # Get more chunks for better context
            filter=filter_dict
        )
        return {"context": retrieved_docs}
    except Exception as e:
        print(f"Retrieval error: {e}")
        return {"context": []}


def generate_answer(state: RAGState):
    """Generate answer using retrieved context"""
    context_docs = state.context
    question = state.question
    
    if not context_docs:
        return {"answer": "I cannot find any relevant information in the uploaded documents to answer your question."}
    
    # Format context with source info
    formatted_context = "\n\n".join([
        f"From '{doc.metadata.get('filename', 'Unknown')}' (chunk {doc.metadata.get('chunk_index', 0) + 1}):\n{doc.page_content}"
        for doc in context_docs
    ])
    
    try:
        answer = rag_chain.invoke({
            "context": formatted_context,
            "question": question
        })
        return {"answer": answer}
    except Exception as e:
        return {"answer": f"Error generating answer: {str(e)}"}


# Build RAG graph
rag_graph_builder = StateGraph(RAGState)
rag_graph_builder.add_sequence([retrieve_documents, generate_answer])
rag_graph_builder.add_edge(START, "retrieve_documents")
rag_graph = rag_graph_builder.compile()
