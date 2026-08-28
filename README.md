# LangChain Text-to-SQL Agent

An Azure Functions HTTP API that uses a LangChain agent and Azure OpenAI to answer natural-language questions about the included SQLite database. The agent inspects the available table schema, generates a read-only SQL query, executes it, and returns a concise answer.

## How It Works

1. Send a question to the `text_to_sql_agent` HTTP endpoint.
2. The agent discovers the tables in `supermarket_sales.db`.
3. It calls `get_table_info` to inspect the relevant schema and sample rows.
4. It generates and executes a `SELECT` query with `execute_sql`.
5. The function returns the agent's final answer as plain text.

The system prompt allows only `SELECT` queries and instructs the agent not to modify the database.

## Prerequisites

- Python 3.10 or later
- Azure Functions Core Tools v4
- An Azure OpenAI resource with a deployment named `gpt-5.4`, or a matching deployment name configured in `agents.py`
- Azure OpenAI credentials with permission to invoke the deployment

## Setup

1. Create and activate a virtual environment:

	 ```powershell
	 python -m venv .venv
	 .\.venv\Scripts\Activate.ps1
	 ```

2. Install the dependencies:

	 ```powershell
	 python -m pip install -r requirements.txt
	 ```

3. Add the Azure OpenAI settings to `local.settings.json` under `Values`:

	 ```json
	 {
		 "AZURE_OPENAI_API_KEY": "your-api-key",
		 "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
		 "OPENAI_API_VERSION": "your-api-version"
	 }
	 ```

	 Keep `local.settings.json` out of source control if it contains secrets. The existing `local.settings.json` contains only the Functions runtime settings, so Azure OpenAI values must be added before starting the function.

4. Confirm that `supermarket_sales.db` is in the project root. The application currently opens this file using a relative path.

## Run Locally

Start the Functions host from the project root:

```powershell
func start
```

The endpoint is:

```text
http://localhost:7071/api/text_to_sql_agent
```

Pass a question in the query string:

```powershell
Invoke-RestMethod -Method Get `
	-Uri "http://localhost:7071/api/text_to_sql_agent?question=What%20is%20the%20total%20sales%20by%20city%3F"
```

Or send it as JSON:

```powershell
Invoke-RestMethod -Method Post `
	-Uri "http://localhost:7071/api/text_to_sql_agent" `
	-ContentType "application/json" `
	-Body '{"question":"How many transactions are in the database?"}'
```

The function uses `FUNCTION` authorization. When deployed to Azure, include a function key using the `code` query parameter or an `x-functions-key` header.

## Project Structure

| File | Description |
| --- | --- |
| `function_app.py` | Defines the HTTP-triggered Azure Function and request handling. |
| `agents.py` | Creates and invokes the LangChain database agent. |
| `tools.py` | Provides SQLite schema inspection and SQL execution tools. |
| `helpers.py` | Reads the table names from the SQLite database. |
| `prompts/system_prompt.txt` | Defines the agent's workflow and SQL restrictions. |
| `supermarket_sales.db` | SQLite database queried by the agent. |
| `host.json` | Azure Functions host configuration. |
| `local.settings.json` | Local Functions and environment settings. |
| `requirements.txt` | Python dependencies. |

## Notes

- Questions must be supplied as `question` in either the query string or JSON request body.
- Missing questions return HTTP `400`.
- Successful requests return the answer as plain text with HTTP `200`.
- Agent or database failures return a generic HTTP `500` response; detailed diagnostics are written to the Functions host logs.
- Conversation state uses an in-memory checkpointer, so it is lost when the Functions process restarts.
