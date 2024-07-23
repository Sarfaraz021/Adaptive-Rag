# -*- coding: utf-8 -*-
"""AdaptiveRAG.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1Q4xXuHo1YMO9QMDQCarPUbbkZeS4a4im
"""

# Commented out IPython magic to ensure Python compatibility.
# %%capture --no-stderr
# ! pip install -U langchain_community tiktoken langchain-openai langchain-cohere langchainhub pinecone-client langchain langgraph  tavily-python "unstructured[pdf]"
# ! pip install langchain_pinecone

import os

os.environ["OPENAI_API_KEY"] = "sk-proj-QkvkEs5F0nXvZUJnlMgcT3BlbkFJJF6SQRqOWucMf78XAUSF"



### Build Index

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone

# Set embeddings
embeddings = OpenAIEmbeddings()

# Docs to index

doc_path = "/content/anjuai.pdf"
# Load
loader =PyPDFLoader(doc_path)
documents = loader.load()
# Split
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500, chunk_overlap=200
)
docs = text_splitter.split_documents(documents)

import os
os.environ["PINECONE_API_KEY"] = "f2ee2cda-ce72-4788-8254-8d33f6a32558"
# Add to vectorstore
Pinecone(environment='us-east-1-aws')
vectorstore = PineconeVectorStore.from_documents(
        documents, embeddings, index_name= "indya-cleo")
retriever = vectorstore.as_retriever()

### Router

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI


# Data model
class RouteQuery(BaseModel):
    """Route a user query to the most relevant datasource."""

    datasource: Literal["vectorstore"] = Field(
        ...,
        description="Given a user question choose to route it to vectorstore.",
    )


# LLM with function call
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
structured_llm_router = llm.with_structured_output(RouteQuery)

# Prompt
system = """You are an expert at routing a user question to a vectorstore.
The vectorstore contains documents about varuns data.
Use the vectorstore for questions on these topics. Otherwise, use your own knowledge"""
route_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "{question}"),
    ]
)

question_router = route_prompt | structured_llm_router

### Generate

from langchain import hub
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
question = " "

#Prompt
# system = """
# You are an assistant for question-answering tasks.
# First, use the following pieces of retrieved context to answer the question.
# If you are unable to find the answer from the given context, then use your own knowledge.
# Finally, if you don't know the answer, just say that you don't know.
# {context}
# """ # Include the context within the system message
# prompt = ChatPromptTemplate.from_messages(
#     [
#         ("system", system),
#         ("human", "{question}"),
#         ("ai", "answer"), # Removed the invalid 'context' message type
#     ]
# )


prompt = hub.pull("indya-cleo")

# LLM
llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)


# Post-processing
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


# Chain
rag_chain = prompt | llm | StrOutputParser()

# Run
# Assuming 'docs' contains your retrieved documents
formatted_docs = format_docs(docs)
generation = rag_chain.invoke({"context": formatted_docs, "question": question})
# print(generation)

"""Graph state"""

from typing import List

from typing_extensions import TypedDict


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        documents: list of documents
    """

    question: str
    generation: str
    documents: List[str]

"""Graph Flow"""

from langchain.schema import Document


def retrieve(state):
    """
    Retrieve documents

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, documents, that contains retrieved documents
    """
    print("---RETRIEVE---")
    question = state["question"]

    # Retrieval
    documents = retriever.invoke(question)
    return {"documents": documents, "question": question}


def generate(state):
    """
    Generate answer

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation, that contains LLM generation
    """
    print("---GENERATE---")
    question = state["question"]
    documents = state["documents"]

    # RAG generation
    generation = rag_chain.invoke({"context": documents, "question": question})
    return {"documents": documents, "question": question, "generation": generation}


### Edges ###


def route_question(state):
    """
    Route question to RAG.

    Args:
        state (dict): The current graph state

    Returns:
        str: Next node to call
    """

    print("---ROUTE QUESTION---")
    question = state["question"]
    source = question_router.invoke({"question": question})
    source.datasource == "vectorstore"
    print("---ROUTE QUESTION TO RAG---")
    return "vectorstore"

"""
Build Graph"""

from langgraph.graph import END, StateGraph, START

workflow = StateGraph(GraphState)

# Define the nodes
workflow.add_node("retrieve", retrieve)  # retrieve
workflow.add_node("generate", generate)  # generatae

# Build graph
workflow.add_conditional_edges(
    START,
    route_question,
    {
        "vectorstore": "retrieve",
    },
)
# workflow.add_edge(""generate")
workflow.add_edge("retrieve", "generate")

# Compile
app = workflow.compile()

from pprint import pprint

# Run
inputs = {
    "question": "Tell me about bluescarf and who is its ceo"
}
iteration_count = 0
for output in app.stream(inputs):
    iteration_count += 1
    print(f"Iteration: {iteration_count}")  # Track iterations
    for key, value in output.items():
        # Node
        pprint(f"Node '{key}':")
        pprint(value) # Print the full state at each node
    pprint("\n---\n")

# Final generation (if reached)
if 'generation' in value:
    pprint(value["generation"])