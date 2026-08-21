from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver

from helpers import get_table_names

from tools import get_table_info, execute_sql

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"
checkpointer = InMemorySaver()

def build_system_prompt() -> str:
    table_list = "\n".join(
        f"- {table}" for table in get_table_names()
    )

    return PROMPT_PATH.read_text(encoding="utf-8").format(table_list=table_list)


def run_database_agent(question: str, thread_id: str = "conversation_1") -> dict:
    model = init_chat_model(
        "gpt-5.4",
        azure_deployment="gpt-5.4",
        model_provider="azure_openai",
    )

    agent = create_agent(
        name="DatabaseAgent",
        model=model,
        tools=[get_table_info, execute_sql],
        system_prompt=build_system_prompt(),
        checkpointer=checkpointer,
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": thread_id}},
    )

    return result

