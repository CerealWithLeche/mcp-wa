from flask import Flask, request, jsonify
from typing import List, Dict, Any, Optional
from collections import defaultdict
import requests
import json
import asyncio
import httpx
import subprocess
import os
import time
from functools import wraps
import websockets
import time

# Configuración inicial
PATH_TO_UV = os.getenv("PATH_TO_UV", "/path/to/uv") #consultar con which uv 
PATH_TO_SRC = os.getenv("PATH_TO_SRC", "/path/to/whatsapp-mcp") #ruta del repositorio colonado
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://localhost:8080")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "api-key")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano-2025-04-14")

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# -------------------------
# Decoradores de utilidad
# -------------------------
def handle_errors(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            app.logger.error(f"Error en {f.__name__}: {str(e)}")
            return {"success": False, "error": str(e)}
    return wrapper

def validate_json(*required_fields):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Se esperaba JSON"}), 400
            
            data = request.get_json()
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return jsonify({"error": f"Campos requeridos faltantes: {', '.join(missing_fields)}"}), 400
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

# -------------------------
# Almacenamiento de estado
# -------------------------
conversation_history = defaultdict(list)
server_status_cache = {"last_checked": 0, "status": None}

# -------------------------
# Funciones de WhatsApp
# -------------------------
from threading import Thread

def check_new_messages(interval=5):
    last_check = time.time()
    while True:
        try:
            response = requests.get(
                f"{WHATSAPP_API_URL}/api/messages?since={int(last_check)}",
                timeout=10
            )
            
            # Depuración: Imprime la respuesta cruda
            print(f"🔍 Respuesta del servidor (status {response.status_code}): {response.text[:100]}...")
            
            # Verifica si la respuesta es JSON válido
            try:
                messages = response.json()
            except json.JSONDecodeError as e:
                print(f"❌ El servidor no devolvió JSON válido: {e}")
                time.sleep(interval)
                continue
                
            # Procesa mensajes
            for msg in messages:
                if msg.get("timestamp", 0) > last_check:
                    print(f"📩 Mensaje válido: {msg}")
                    asyncio.create_task(process_incoming_message(msg["from"], msg["body"]))
                    last_check = msg["timestamp"]
                    
        except Exception as e:
            print(f"❌ Error en polling: {str(e)}")
        time.sleep(interval)

async def listen_whatsapp_events():
    """Conéctate al WebSocket del servidor WhatsApp y escucha mensajes"""
    ws_url = WHATSAPP_API_URL.replace("http", "ws") + "/events"  # Ej: ws://localhost:8080/events
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                print("✅ Conectado al WebSocket de WhatsApp")
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    if data.get("type") == "message":
                        print(f"📩 Mensaje recibido: {data}")
                        asyncio.create_task(
                            process_incoming_message(data["from"], data["body"])
                        )
        except Exception as e:
            print(f"❌ Error en WebSocket: {e}. Reconectando en 5 segundos...")
            await asyncio.sleep(5)
                
async def process_incoming_message(sender: str, message: str):
    """Procesa mensajes entrantes y genera respuestas"""
    try:
        # 1. Prepara el payload para OpenAI
        messages = conversation_history.get(sender, [])
        messages.insert(0, {
            "role": "system",
            "content": "Eres un asistente de WhatsApp. Responde de forma concisa y útil."
        })
        
        # 2. Llama a OpenAI
        response = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": messages
            }
        )
        response.raise_for_status()
        ai_response = response.json()["choices"][0]["message"]["content"]

        # 3. Envía la respuesta
        send_response = send_message(sender, ai_response)
        if send_response.get("success"):
            conversation_history[sender].append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": time.time()
            })
            
    except Exception as e:
        app.logger.error(f"Error procesando mensaje: {str(e)}")
        # Opcional: Enviar mensaje de error al usuario
        send_message(sender, "⚠️ Ocurrió un error al procesar tu mensaje")
        
@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para recibir mensajes entrantes de WhatsApp"""
    data = request.get_json()
    app.logger.info(f"Mensaje recibido: {json.dumps(data, indent=2)}")

    # Procesar solo mensajes de texto (ignorar estados, etc.)
    if data.get("type") == "message" and data.get("body"):
        sender = data["from"]
        message = data["body"]
        
        # Guardar en historial
        conversation_history[sender].append({
            "role": "user",
            "content": message,
            "timestamp": time.time()
        })

        # Procesar mensaje en segundo plano
        asyncio.create_task(process_incoming_message(sender, message))
    
    return jsonify({"status": "received"}), 200
##############################################

@app.route("/send-to-contact", methods=["POST"])
@validate_json("contact_name", "message")
def send_to_contact():
    """Envía mensaje a un contacto buscándolo por nombre"""
    data = request.get_json()
    contact_name = data["contact_name"]
    message = data["message"]

    # Busca el contacto
    contacts = search_contacts(contact_name, limit=1)
    if not contacts:
        return jsonify({
            "success": False,
            "error": f"No se encontró el contacto '{contact_name}'"
        }), 404

    # Envía el mensaje
    recipient_jid = contacts[0]["jid"]
    response = send_message(recipient_jid, message)

    return jsonify({
        "success": response.get("success", False),
        "message": response.get("message", ""),
        "contact": contacts[0]
    })
    
@handle_errors
def get_contacts() -> List[Dict]:
    """Obtiene la lista completa de contactos con caché"""
    try:
        response = requests.get(f"{WHATSAPP_API_URL}/api/contacts", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error al obtener contactos: {str(e)}")
        return []

@handle_errors
def find_contact(search_term: str) -> Optional[Dict]:
    """Busca un contacto con coincidencia parcial"""
    contacts = get_contacts()
    search_term = search_term.lower().strip()
    
    # Primero busqueda exacta
    exact_match = next((c for c in contacts if c["name"].lower() == search_term), None)
    if exact_match:
        return exact_match
    
    # Luego coincidencias parciales
    partial_match = next((c for c in contacts if search_term in c["name"].lower()), None)
    return partial_match

@handle_errors
def send_message(recipient: str, message: str) -> Dict:
    """Envía mensajes aceptando números o nombres de contacto"""
    # Si es un nombre (no empieza con dígito)
    if not recipient[0].isdigit():
        contact = find_contact(recipient)
        if not contact:
            available_contacts = [c["name"] for c in get_contacts()[:3]]
            return {
                "success": False,
                "error": f"Contacto '{recipient}' no encontrado. Contactos disponibles: {', '.join(available_contacts)}"
            }
        recipient = contact["jid"]
    else:
        # Normalización de números
        clean_number = "".join(c for c in recipient if c.isdigit())
        if not clean_number.startswith('521'):
            if clean_number.startswith('52'):
                clean_number = '521' + clean_number[2:]
            elif clean_number.startswith('1'):
                clean_number = '521' + clean_number[1:]
            else:
                clean_number = '521' + clean_number
        
        if len(clean_number) < 12 or len(clean_number) > 13:
            return {"success": False, "error": "Formato de número inválido"}
        
        recipient = clean_number

    response = requests.post(
        f"{WHATSAPP_API_URL}/api/send",
        json={"recipient": recipient, "message": message},
        timeout=10
    )
    response.raise_for_status()
    
    return {
        "success": True,
        "message": f"Mensaje enviado a {recipient}",
        "recipient": recipient,
        "status": "sent"  # Campo adicional para claridad
    }

@handle_errors
def search_contacts(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Busca contactos en WhatsApp por nombre o número"""
    contacts = get_contacts()
    query = query.lower().strip()
    
    return [
        {
            "name": c["name"],
            "jid": c["jid"],
            "phone": c["jid"].split("@")[0] if "@" in c["jid"] else c["jid"]
        }
        for c in contacts
        if query in c["name"].lower() or query in c["jid"].lower()
    ][:limit]

@handle_errors
def control_whatsapp_server(action: str) -> Dict:
    """Controla el servidor de WhatsApp"""
    if action == "start":
        if is_whatsapp_server_running():
            return {"status": "success", "message": "Servidor ya está en ejecución"}
            
        process = subprocess.Popen(
            [PATH_TO_UV, "run", "--host", "0.0.0.0", "--port", "8000", f"{PATH_TO_SRC}/whatsapp-mcp-server/main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PATH_TO_SRC
        )
        
        time.sleep(2)
        if is_whatsapp_server_running():
            return {"status": "success", "message": "Servidor iniciado", "pid": process.pid}
        return {"status": "error", "message": "No se pudo iniciar el servidor"}
        
    elif action == "stop":
        subprocess.run(["pkill", "-f", "uv.*whatsapp-mcp-server"], check=True)
        return {"status": "success", "message": "Servidor detenido"}

def is_whatsapp_server_running() -> bool:
    """Verifica si el servidor está respondiendo con caché"""
    now = time.time()
    if now - server_status_cache["last_checked"] < 5 and server_status_cache["status"] is not None:
        return server_status_cache["status"]
    
    try:
        response = requests.get(f"{WHATSAPP_API_URL}/status", timeout=2)
        server_status_cache["status"] = response.status_code == 200
        server_status_cache["last_checked"] = now
        return server_status_cache["status"]
    except:
        server_status_cache["status"] = False
        server_status_cache["last_checked"] = now
        return False

# -------------------------
# Funciones generales
# -------------------------
@handle_errors
def sumar(a: int, b: int) -> Dict:
    """Suma dos números."""
    return {"resultado": a + b}

@handle_errors
async def buscar_repos(query: str) -> List[Dict]:
    """Busca repositorios en GitHub."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/search/repositories?q={query}&sort=stars",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10
        )
        response.raise_for_status()
        repos = response.json()["items"][:3]
        return [{
            "name": repo["full_name"],
            "description": repo["description"],
            "stars": repo["stargazers_count"],
            "url": repo["html_url"]
        } for repo in repos]

# -------------------------------
# Configuración de herramientas
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
    },
    {
        "name": "control_whatsapp_server",
        "description": "Inicia o detiene el servidor de WhatsApp MCP.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "stop"], "description": "Acción a realizar."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_message",
        "description": "Envía un mensaje por WhatsApp.",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "Número (521...) o nombre del contacto"},
                "message": {"type": "string", "description": "Contenido del mensaje"}
            },
            "required": ["recipient", "message"]
        }
    },
    {
        "name": "search_contacts",
        "description": "Busca contactos de WhatsApp por nombre o número de teléfono.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Término de búsqueda (nombre o número)"},
                "limit": {"type": "integer", "description": "Límite de resultados", "default": 5}
            },
            "required": ["query"]
        }
    }
]

# --------------------------
# Endpoints
# --------------------------
@app.route("/health")
def health_check():
    """Endpoint de verificación de estado"""
    return jsonify({
        "flask": "running",
        "uv_process": "running" if is_whatsapp_server_running() else "not running",
        "mcp_server": "running" if is_whatsapp_server_running() else "unreachable"
    })

@app.route("/search-contacts", methods=["POST"])
@validate_json("query")
def search_contacts_endpoint():
    data = request.get_json()
    contacts = search_contacts(data["query"], data.get("limit", 5))
    return jsonify({"success": True, "count": len(contacts), "contacts": contacts})

@app.route("/send-message", methods=["POST"])
@validate_json("recipient", "message")
def send_message_endpoint():
    data = request.get_json()
    response = send_message(data["recipient"], data["message"])
    status_code = 200 if response.get("success") else 400
    return jsonify(response), status_code

@app.route("/mcp-to-openai", methods=["POST"])
@validate_json("input")
def mcp_to_openai():
    data = request.get_json()
    user_input = data["input"]
    session_id = data.get("session_id", "default")
    
    # Preparar mensajes
    messages = conversation_history[session_id][-10:]  # Mantener solo los últimos 10 mensajes
    messages.insert(0, {"role": "system", "content": "Eres un asistente útil. Responde de forma concisa."})
    messages.append({"role": "user", "content": user_input})
    
    # Configurar payload para OpenAI
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "functions": functions,
        "function_call": "auto"
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        # Primera llamada a OpenAI
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        message = result["choices"][0]["message"]
        
        # Si no se usó función
        if "function_call" not in message:
            response_message = message.get("content", "No puedo responder a eso.")
            tool_used = False
            tool_name = None
            output = None
        else:
            # Procesar función
            func_call = message["function_call"]
            func_name = func_call["name"]
            func_args = json.loads(func_call["arguments"])
            
            # Ejecutar función
            if func_name == "control_whatsapp_server":
                output = control_whatsapp_server(**func_args)
            elif func_name == "sumar":
                output = sumar(**func_args)
            elif func_name == "buscar_repos":
                output = asyncio.run(buscar_repos(**func_args))
            # En la función mcp_to_openai(), modifica el manejo de send_message:
            elif func_name == "send_message":
                # Primero busca los contactos
                contacts = search_contacts(func_args["recipient"])
                
                # Si hay exactamente un contacto, envía directamente
                if len(contacts) == 1:
                    output = send_message(contacts[0]["jid"], func_args["message"])
                    return jsonify({
                        "response": f"Mensaje enviado a {contacts[0]['name']}",
                        "tool_used": True,
                        "tool_name": "send_message",
                        "output": output,
                        "direct_send": True  # Indica que fue un envío directo
                    })
                
                # Si hay múltiples contactos
                elif len(contacts) > 1:
                    output = {
                        "multiple_contacts": True,
                        "options": contacts,
                        "original_message": func_args["message"]
                    }
                    contact_list = "\n".join([f"{c['name']} ({c['phone']})" for c in contacts])
                    response_message = f"Varios contactos encontrados:\n{contact_list}\n¿A cuál deseas enviar el mensaje?"
                
                # Si no hay contactos
                else:
                    output = {"success": False, "error": "No se encontró el contacto"}
                    response_message = "No encontré ese contacto en la lista"
                
                tool_used = True
                tool_name = func_name
            elif func_name == "search_contacts":
                output = search_contacts(**func_args)
            else:
                return jsonify({"error": f"Función '{func_name}' no permitida"}), 400

            tool_used = True
            tool_name = func_name

            # Segunda llamada para responder con el resultado
            messages.append({
                "role": "assistant",
                "content": None,
                "function_call": func_call
            })
            messages.append({
                "role": "function",
                "name": func_name,
                "content": json.dumps(output)
            })

            second_response = requests.post(
                OPENAI_API_URL,
                headers=headers,
                json={"model": OPENAI_MODEL, "messages": messages}
            )
            second_response.raise_for_status()
            response_message = second_response.json()["choices"][0]["message"]["content"]

        # Actualizar historial
        conversation_history[session_id].extend([
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_message}
        ])

        return jsonify({
            "response": response_message,
            "session_id": session_id,
            "tool_used": tool_used,
            "tool_name": tool_name,
            "output": output
        })

    except requests.exceptions.HTTPError as err:
        app.logger.error(f"Error en OpenAI: {err.response.text}")
        return jsonify({"error": f"Error en la API: {err.response.status_code}"}), 500
    except Exception as e:
        app.logger.error(f"Error inesperado: {str(e)}")
        return jsonify({"error": f"Error inesperado: {str(e)}"}), 500

# Inicia el polling en un hilo separado al arrancar Flask
polling_thread = Thread(target=check_new_messages, daemon=True)
polling_thread.start()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    
