from flask import Flask, request, jsonify
from collections import defaultdict
import requests
import json
import asyncio
import httpx

app = Flask(__name__)

# -------------------------
# Configuración de OpenAI
# -------------------------
OPENAI_API_KEY = "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"  # Reemplaza con tu API key de OpenAI
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4.1-nano-2025-04-14"  # o "gpt-3.5-turbo-1106" si estás usando function calling

# --------------------------
# Almacenamiento de conversaciones
# --------------------------
conversation_history = defaultdict(list)

# --------------------------
# Definición de herramientas
# --------------------------


def sumar(a: int, b: int) -> dict:
    return {"resultado": a + b}

async def buscar_repos(query: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.github.com/search/repositories?q={query}"
            response = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
            response.raise_for_status()
            data = response.json()
            return [{
                'name': repo['full_name'],
                'description': repo['description'],
                'url': repo['html_url'],
                'stars': repo['stargazers_count'],
                'language': repo['language']
            } for repo in data.get('items', [])[:5]]
        except httpx.HTTPStatusError as e:
            return {"error": f"Error al buscar repositorios: {str(e)}"}

# -------------------------------
# Lista de funciones para OpenAI
# -------------------------------
functions = [
    {
        "name": "sumar",
        "description": "Suma dos numeros enteros.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "Primer número"},
                "b": {"type": "integer", "description": "Segundo número"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "buscar_repos",
        "description": "Busca repositorios populares en GitHub relacionados con un término dado.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Término de búsqueda para GitHub"}
            },
            "required": ["query"]
        }
    }
]

# ---------------------
# Endpoint principal
# ---------------------
@app.route("/mcp-to-openai", methods=["POST"])
def mcp_to_openai():
    if not request.is_json:
        return jsonify({"error": "Se esperaba JSON"}), 400
    
    data = request.get_json()
    user_input = data.get("input", "")
    session_id = data.get("session_id", "default")

    if not user_input:
        return jsonify({"error": "El campo 'input' es requerido"}), 400

    # Preparar mensajes
    messages = conversation_history[session_id].copy()
    messages.insert(0, {"role": "system", "content": "Eres un asistente útil."})
    messages.append({"role": "user", "content": user_input})

    use_tools = not user_input.lower().startswith(('hola', 'hi', 'hello'))

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages
    }
    
    if use_tools:
        payload.update({
            "functions": functions,  
            "function_call": "auto"  
        })

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.HTTPError as err:
        return jsonify({
            "error": f"Error en la API: {err.response.status_code}",
            "details": err.response.text
        }), 500
    except Exception as e:
        return jsonify({"error": f"Error de conexión: {str(e)}"}), 500

    message = result["choices"][0]["message"]
    tool_used = False
    tool_name = None
    output = None

    # Si no se usó función
    if "function_call" not in message:
        response_message = message.get("content", "No puedo responder a eso.")
    else:
        func_call = message["function_call"]
        func_name = func_call["name"]
        func_args = json.loads(func_call["arguments"])

        try:
            if func_name == "sumar":
                output = sumar(**func_args)
            elif func_name == "buscar_repos":
                output = asyncio.run(buscar_repos(**func_args))
            else:
                return jsonify({"error": f"Función '{func_name}' no permitida"}), 400

            tool_used = True
            tool_name = func_name

            # Segunda llamada para responder con el resultado de la función
            second_payload = {
                "model": OPENAI_MODEL,
                "messages": [
                    *messages,
                    {
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": func_name,
                            "arguments": json.dumps(func_args)
                        }
                    },
                    {
                        "role": "function",
                        "name": func_name,
                        "content": json.dumps(output)
                    }
                ]
            }

            second_response = requests.post(OPENAI_API_URL, headers=headers, json=second_payload)
            second_response.raise_for_status()
            second_result = second_response.json()
            response_message = second_result["choices"][0]["message"]["content"]

        except Exception as e:
            return jsonify({"error": f"Error procesando herramienta: {str(e)}"}), 500

    # Guardar historial
    conversation_history[session_id].extend([
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": response_message}
    ])

    # Limitar historial
    if len(conversation_history[session_id]) > 10:
        conversation_history[session_id] = conversation_history[session_id][-10:]

    return jsonify({
        "response": response_message,
        "session_id": session_id,
        "tool_used": tool_used,
        "tool_name": tool_name,
        "output": output
    })

# ---------------------
# Ejecutar servidor
# ---------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
