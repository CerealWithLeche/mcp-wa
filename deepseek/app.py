from flask import Flask, request, jsonify
from collections import defaultdict
import requests
import json
import asyncio
import httpx

app = Flask(__name__)

# -------------------------
# Configuración de DeepSeek
# -------------------------
DEEPSEEK_API_KEY = "api-key"  
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# --------------------------
# Almacenamiento de conversaciones
# --------------------------
conversation_history = defaultdict(list)

# --------------------------
# Definición de herramientas
# --------------------------
def sumar(a: int, b: int) -> dict:
    """Suma dos números enteros y devuelve el resultado en un diccionario"""
    return {"resultado": a + b}

async def buscar_repos(query: str) -> list[dict]:
    """Busca repositorios en GitHub y retorna su información"""
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.github.com/search/repositories?q={query}"
            response = await client.get(
                url, 
                headers={"Accept": "application/vnd.github.v3+json"}
            )
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
# Lista de herramientas para DeepSeek
# -------------------------------
tools = [
    {
        "type": "function",
        "function": {
            "name": "sumar",
            "description": "Suma dos numeros enteros.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "Primer numero"},
                    "b": {"type": "integer", "description": "Segundo numero"}
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
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
    }
]

# ---------------------
# Endpoint principal
# ---------------------
@app.route("/mcp-to-deepseek", methods=["POST"])
@app.route("/mcp-to-deepseek", methods=["POST"])
def mcp_to_deepseek():
    # Validación de entrada
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

    # Configurar tools solo si no es saludo
    use_tools = not user_input.lower().startswith(('hola', 'hi', 'hello'))
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "tools": tools if use_tools else None,
        "tool_choice": "auto" if use_tools else None
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()  # Esto lanzará error para códigos 4xx/5xx
        result = response.json()
    except requests.exceptions.HTTPError as err:
        return jsonify({
            "error": f"Error en la API: {err.response.status_code}",
            "details": err.response.text
        }), 500
    except Exception as e:
        return jsonify({"error": f"Error de conexión: {str(e)}"}), 500

    # Verificar respuesta de DeepSeek
    if "choices" not in result or not result["choices"]:
        return jsonify({"error": "Respuesta inválida de DeepSeek"}), 500

    message = result["choices"][0]["message"]
    tool_used = False
    tool_name = None
    output = None

    # Caso 1: Respuesta directa (sin herramientas)
    if "tool_calls" not in message or not message["tool_calls"]:
        response_message = message.get("content", "No puedo responder a eso")
    else:
        # Caso 2: Uso de herramientas
        tool_call = message["tool_calls"][0]
        func_name = tool_call["function"]["name"]
        func_args = json.loads(tool_call["function"]["arguments"])

        try:
            if func_name == "sumar":
                output = sumar(**func_args)
            elif func_name == "buscar_repos":
                output = asyncio.run(buscar_repos(**func_args))
            else:
                return jsonify({"error": f"Función '{func_name}' no permitida"}), 400
            
            tool_used = True
            tool_name = func_name

            # Segunda llamada a DeepSeek con el resultado
            second_payload = {
                "model": "deepseek-chat",
                "messages": [
                    *messages,
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call["id"],
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "arguments": tool_call["function"]["arguments"]
                                }
                            }
                        ]
                    },
                    {
                        "role": "tool",
                        "content": json.dumps(output),
                        "tool_call_id": tool_call["id"]
                    }
                ],
                "tool_choice": "none"
            }

            second_response = requests.post(DEEPSEEK_API_URL, headers=headers, json=second_payload)
            second_response.raise_for_status()
            final_result = second_response.json()
            response_message = final_result["choices"][0]["message"]["content"]
            
        except Exception as e:
            return jsonify({"error": f"Error procesando herramienta: {str(e)}"}), 500

    # Guardar en el historial de conversación
    conversation_history[session_id].extend([
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": response_message}
    ])

    # Limitar el historial para no sobrecargar la memoria
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