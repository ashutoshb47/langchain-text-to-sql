import azure.functions as func
import logging

from agents import run_database_agent

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="text_to_sql_agent")
def text_to_sql_agent(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    question = req.params.get("question")
    if not question:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            question = req_body.get("question")

    if not question:
        return func.HttpResponse(
            "Pass a question in the query string or request body.",
            status_code=400,
        )

    try:
        result = run_database_agent(question)

        for message in result["messages"]:
            logging.info(
                "Agent message (%s): %s",
                message.__class__.__name__,
                message.content,
            )

            for tool_call in getattr(message, "tool_calls", []):
                logging.info(
                    "Tool call: %s with arguments %s",
                    tool_call["name"],
                    tool_call["args"],
                )

        answer = result["messages"][-1].content
    except Exception:
        logging.exception("Database agent request failed.")
        return func.HttpResponse("Unable to answer the question.", status_code=500)

    return func.HttpResponse(answer, status_code=200)