from typing import Annotated, Literal, Optional, TypedDict, List
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph.message import add_messages

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from get_prompts import load_system_prompt
from tools import execute_sql, get_table_info

import json, os, uuid

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # headless backend, no GUI needed
import matplotlib.pyplot as plt



llm = AzureChatOpenAI(model="gpt-5.4")

class AgentState(TypedDict):
    # add_messages allows us to append to the history rather than overwriting it
    messages: Annotated[List[BaseMessage], add_messages]
    next_step: str
    quality_score: int
    needs_pie_chart: bool
    chart_reason: Optional[str]
    chart_path: Optional[str]     # PNG file path
    chart_data: Optional[dict]

class VisualizationDecision(BaseModel):
    needs_pie_chart: bool = Field(
        description="True only if the data shows parts of a whole (proportions, "
                    "percentages, category shares) that suit a pie chart."
    )
    reason: str = Field(description="One-sentence justification.")

classifier_llm = llm.with_structured_output(VisualizationDecision)

CLASSIFIER_PROMPT = SystemMessage(content=(
    "You are a data visualization analyst for a supermarket sales database. "
    "You will receive the output of a database agent, which contains rows and "
    "columns of sales data (for example: item, category, units sold, revenue, "
    "date, store).\n\n"
    "Analyze the table and decide whether a pie chart is appropriate.\n\n"
    "Answer TRUE only if ALL of these hold:\n"
    "1. There is one categorical column (item, product category, store, payment "
    "method, etc.) and one numeric measure (revenue, units sold, quantity, "
    "profit).\n"
    "2. The numeric values are non-negative and add up to a meaningful whole, "
    "such as total sales or total units.\n"
    "3. The question is about composition or share: how each item or category "
    "contributes to the total.\n"
    "4. There are roughly 2 to 8 categories, or the data can be sensibly grouped "
    "into that many (for example, top items plus 'Other').\n\n"
    "Answer FALSE if any of these apply:\n"
    "- The data is a time series or trend (sales by day, month, or year).\n"
    "- The result is a single value or a single row.\n"
    "- The data compares many metrics per item (price, cost, stock, revenue) "
    "rather than one measure across categories.\n"
    "- The values include negatives (returns, losses) or are averages, rates, or "
    "prices that don't sum meaningfully.\n"
    "- There are too many categories (more than about 10) with no clear way to "
    "group them.\n"
    "- The output is plain text, an error message, or an empty result.\n\n"
    "In your reason, name the category column and the numeric column you would "
    "use for the chart, or explain why a pie chart is not suitable."
))


tools = [get_table_info, execute_sql]

llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)

def get_last_query_result(messages) -> dict | None:
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "execute_sql":
            try:
                data = json.loads(msg.content)
            except json.JSONDecodeError:
                return None
            return None if "error" in data else data
    return None

def database_node(state: AgentState):
    messages = state['messages']
    system_prompt = SystemMessage(content=load_system_prompt("database"))
    response = llm_with_tools.invoke([system_prompt] + state["messages"])

    result = get_last_query_result(state["messages"])
    if result is None or result["row_count"] < 2:
        return {"messages": [response], "needs_pie_chart": False,
                "chart_reason": "No usable multi-row query result."}

    # Model wants to call tools: return and let the graph route to the tool node
    if response.tool_calls:
        return {"messages": [response]}

    decision = classifier_llm.invoke([
        CLASSIFIER_PROMPT,
        ("human", f"User question: {state['messages'][0].content}\n\n"
                  f"Query result (JSON):\n{json.dumps(result)}"),
    ])

    return {
        "messages": [response],
        "needs_pie_chart": decision.needs_pie_chart,
        "chart_reason": decision.reason,
    }


class PieChartSpec(BaseModel):
    category_column: str = Field(description="Column whose values become the pie slices.")
    value_column: str = Field(description="Numeric column that sets the slice sizes.")
    title: str = Field(description="Short, descriptive chart title.")
    max_slices: int = Field(
        default=8, ge=2, le=10,
        description="Max slices to show; the rest are grouped into 'Other'.",
    )

chart_llm = llm.with_structured_output(PieChartSpec)

CHART_DIR = "charts"
os.makedirs(CHART_DIR, exist_ok=True)

COLUMN_PICKER_INSTRUCTIONS = (
    "\n\nYou will be given a user question and a query result (column names and "
    "sample rows). Choose the single categorical column and the single numeric "
    "column that best answer the question as a share-of-total pie chart. "
    "Only use column names that exist in the data."
)

def visual_node(state: AgentState):
    result = get_last_query_result(state["messages"])
    if result is None or not result["rows"]:
        return {"messages": [AIMessage(content="No query data available to visualize.")]}

    df = pd.DataFrame(result["rows"], columns=result["columns"])

    # 1. LLM picks the columns (it sees only a small sample)
    question = state["messages"][0].content
    system_prompt = SystemMessage(content=load_system_prompt("visual") + COLUMN_PICKER_INSTRUCTIONS)
    spec = chart_llm.invoke([
        system_prompt,
        ("human",
         f"User question: {question}\n"
         f"Why a pie chart: {state.get('chart_reason')}\n"
         f"Columns: {result['columns']}\n"
         f"Sample rows: {df.head(5).to_dict('records')}"),
    ])

    # 2. Validate the choice against the real data
    for col in (spec.category_column, spec.value_column):
        if col not in df.columns:
            return {"messages": [AIMessage(content=f"Could not build chart: column '{col}' not found.")]}

    df[spec.value_column] = pd.to_numeric(df[spec.value_column], errors="coerce")
    df = df.dropna(subset=[spec.value_column])
    df = df[df[spec.value_column] > 0]
    if len(df) < 2:
        return {"messages": [AIMessage(content="Not enough positive values to draw a pie chart.")]}

    # 3. Aggregate duplicates, sort, and group the tail into "Other"
    grouped = (
        df.groupby(spec.category_column, as_index=False)[spec.value_column]
          .sum()
          .sort_values(spec.value_column, ascending=False)
    )
    if len(grouped) > spec.max_slices:
        top = grouped.iloc[: spec.max_slices - 1]
        other_total = grouped.iloc[spec.max_slices - 1 :][spec.value_column].sum()
        other = pd.DataFrame({spec.category_column: ["Other"], spec.value_column: [other_total]})
        grouped = pd.concat([top, other], ignore_index=True)

    labels = grouped[spec.category_column].astype(str).tolist()
    values = grouped[spec.value_column].tolist()

    # 4. Render the chart
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90, counterclock=False)
    ax.set_title(spec.title)
    ax.axis("equal")

    chart_path = os.path.join(CHART_DIR, f"pie_{uuid.uuid4().hex[:8]}.png")
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    chart_data = {"labels": labels, "values": values, "title": spec.title}

    return {
        "messages": [AIMessage(content=f"Pie chart created: {spec.title} (saved to {chart_path})")],
        "chart_path": chart_path,
        "chart_data": chart_data,
    }


workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("database", database_node)
workflow.add_node("tools", tool_node)
workflow.add_node("visual", visual_node)

# Define Edges
workflow.set_entry_point("database")
workflow.add_edge("tools", "database")   # loop back so the LLM sees tool results
workflow.add_edge("visual", END)

def route_after_database(state: AgentState) -> Literal["tools", "visual", "end"]:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "visual" if state.get("needs_pie_chart") else "end"

workflow.add_conditional_edges(
    "database",
    route_after_database,
    {
        "tools": "tools",
        "visual": "visual",
        "end": END,
    },
)



app = workflow.compile()

def print_message(msg, indent="   "):
    if isinstance(msg, AIMessage):
        print(f"{indent}[AIMessage]")
        if msg.content:
            print(f"{indent}  content: {msg.content}")
        for tc in msg.tool_calls:
            print(f"{indent}  tool_call: {tc['name']}({json.dumps(tc['args'])})")
        usage = msg.usage_metadata
        if usage:
            print(f"{indent}  tokens: in={usage.get('input_tokens')} out={usage.get('output_tokens')}")
    elif isinstance(msg, ToolMessage):
        content = msg.content
        if len(content) > 600:
            content = content[:600] + f"... [{len(msg.content)} chars total]"
        print(f"{indent}[ToolMessage name={msg.name}]")
        print(f"{indent}  content: {content}")
    else:
        print(f"{indent}[{type(msg).__name__}] {msg.content}")


def run_with_trace(question: str, recursion_limit: int = 25):
    inputs = {"messages": [HumanMessage(content=question)]}
    config = {"recursion_limit": recursion_limit}

    print("=" * 80)
    print(f"USER QUESTION: {question}")
    print("=" * 80)

    final_state = dict(inputs)  # we rebuild the final state from the updates
    step = 0

    for chunk in app.stream(inputs, config=config, stream_mode="updates"):
        for node_name, update in chunk.items():
            step += 1
            print(f"\n--- STEP {step}: node '{node_name}' ---")

            if not update:
                print("   (no state update)")
                continue

            for key, value in update.items():
                if key == "messages":
                    for m in value:
                        print_message(m)
                else:
                    print(f"   {key}: {value}")

            # keep a running copy of non-message fields
            for key, value in update.items():
                if key == "messages":
                    final_state["messages"] = final_state["messages"] + value
                else:
                    final_state[key] = value

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"Total steps      : {step}")
    print(f"Total messages   : {len(final_state['messages'])}")
    print(f"needs_pie_chart  : {final_state.get('needs_pie_chart')}")
    print(f"chart_reason     : {final_state.get('chart_reason')}")
    print(f"chart_path       : {final_state.get('chart_path')}")
    print(f"chart_data       : {final_state.get('chart_data')}")

    return final_state


if __name__ == "__main__":
    final = run_with_trace("what are the total sales by Ship Mode?")

