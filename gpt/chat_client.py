import requests
import json
from uuid import uuid4
import sys
import readline
import re

# Configuración
API_URL = "http://localhost:5000/mcp-to-openai"
SESSION_ID = str(uuid4())
REQUEST_TIMEOUT = 30  # segundos

# Colores para la terminal
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_color(text, color):
    """Imprime texto en color con formato."""
    print(f"{color}{text}{Colors.END}")

def print_tool_response(tool_name, output):
    """Muestra respuestas de herramientas con formato."""
    if not output:
        return

    # Si output es una lista (ej: search_contacts)
    if isinstance(output, list):
        if tool_name == "search_contacts":
            print_color(f"\n👥 Contactos encontrados ({len(output)}):", Colors.BLUE)
            for contact in output:
                print_color(f"  👤 {contact.get('name', 'Sin nombre')}", Colors.BLUE)
                print_color(f"  📞 {contact.get('phone', 'N/A')}", Colors.BLUE)
        else:
            print_color(f"\n[Herramienta: {tool_name}]\n{json.dumps(output, indent=2)}", Colors.YELLOW)
        return

    # Si output es un diccionario
    if tool_name == "sumar":
        print_color(f"\n🔢 Resultado: {output.get('resultado', '?')}", Colors.CYAN)
    elif tool_name == "buscar_repos":
        print_color("\n📂 Repositorios encontrados:", Colors.PURPLE)
        for repo in output:
            print_color(f"\n  🏷️ {repo.get('name', 'Sin nombre')}", Colors.PURPLE)
            print_color(f"  📝 {repo.get('description', 'Sin descripción')}", Colors.PURPLE)
            print_color(f"  ⭐ {repo.get('stars', 'N/A')} estrellas", Colors.PURPLE)
            print_color(f"  🔗 {repo.get('url', 'No disponible')}", Colors.PURPLE)
    elif tool_name == "send_message":
        if output.get("success"):
            print_color(f"\n✅ Mensaje enviado a {output.get('recipient', 'N/A')}:", Colors.GREEN)
            print_color(f"  💬 {output.get('message', '')}", Colors.GREEN)
        else:
            print_color(f"\n❌ Error: {output.get('error', output.get('message', 'Error desconocido'))}", Colors.RED)
    elif tool_name == "control_whatsapp_server":
        status = "🟢 Encendido" if output.get("status") == "success" else "🔴 Apagado/Error"
        print_color(f"\n🖥️ Estado del servidor: {status}", Colors.YELLOW)
        print_color(f"  📌 Mensaje: {output.get('message', 'N/A')}", Colors.YELLOW)
    else:
        print_color(f"\n[Herramienta: {tool_name}]\n{json.dumps(output, indent=2)}", Colors.YELLOW)

def check_server_connection():
    """Verifica si el servidor está disponible."""
    try:
        response = requests.get(f"{API_URL.replace('/mcp-to-openai', '/health')}", timeout=2)
        return response.status_code == 200
    except:
        return False

def send_chat_request(user_input):
    """Envía la solicitud al servidor."""
    payload = {
        "input": user_input,
        "session_id": SESSION_ID
    }
    
    try:
        response = requests.post(
            API_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print_color(f"\n❌ Error {response.status_code}:", Colors.RED)
            print_color(response.text, Colors.RED)
            return None
            
    except requests.exceptions.Timeout:
        print_color("\n⌛ Tiempo de espera agotado. ¿El servidor está ocupado?", Colors.RED)
    except requests.exceptions.ConnectionError:
        print_color("\n🔌 Error de conexión: ¿El servidor está corriendo?", Colors.RED)
    #except Exception as e:
     #   print_color(f"\n⚠️ Error inesperado: {str(e)}", Colors.RED)
    
    return None

def chat():
    """Bucle principal del chat."""
    if not check_server_connection():
        print_color("\n🔴 No se pudo conectar al servidor. Por favor inicia app.py primero.", Colors.RED)
        return

    print_color("\n🌟 Bienvenido al chat con DeepSeek", Colors.BLUE)
    print_color(f"📌 Session ID: {SESSION_ID}", Colors.YELLOW)
    print_color("✍️ Escribe 'salir' para terminar\n", Colors.GREEN)
    
    while True:
        try:
            user_input = input(f"{Colors.BOLD}Tú:{Colors.END} ").strip()
            if user_input.lower() in ['salir', 'exit', 'quit']:
                print_color("\n👋 ¡Hasta luego!", Colors.BLUE)
                break
            
            response = send_chat_request(user_input)
            
            if response:
                # Si hay output de herramientas (como resultados de búsqueda)
                if response.get('output'):
                    # Caso: Búsqueda de contactos (output es lista)
                    if isinstance(response['output'], list):
                        contacts = response['output']
                        print_tool_response(response['tool_name'], contacts)  # Muestra los contactos
                        
                        # Si hay exactamente 1 contacto
                        if len(contacts) == 1:
                            contact = contacts[0]
                            message = extract_message_from_input(user_input)
                            
                            if message:
                                # Elimina palabras sobrantes como "que", "diciendo", etc.
                                message = re.sub(r'^(?:que|diciendo|con el mensaje)\s*', '', message, flags=re.IGNORECASE)
                                print_color(f"\n✉️ Mensaje detectado: '{message}'", Colors.CYAN)
                                send_response = requests.post(
                                    "http://localhost:5000/send-to-contact",
                                    json={
                                        "contact_name": contact.get('name'),
                                        "message": message
                                    }
                                )
                                if send_response.status_code == 200:
                                    print_color(f"\n✅ Mensaje enviado a {contact.get('name')}: {message}", Colors.GREEN)
                                else:
                                    print_color(f"\n❌ Error al enviar: {send_response.text}", Colors.RED)
                            else:
                                # Si no se extrajo el mensaje, pedir confirmación
                                confirm = input(f"\n¿Enviar mensaje a {contact.get('name')}? (s/n): ").strip().lower()
                                if confirm == 's':
                                    msg = input("Mensaje a enviar: ").strip()
                                    send_response = requests.post(
                                        "http://localhost:5000/send-to-contact",
                                        json={
                                            "contact_name": contact.get('name'),
                                            "message": msg
                                        }
                                    )
                                    if send_response.status_code == 200:
                                        print_color(f"\n✅ Mensaje enviado: {msg}", Colors.GREEN)
                        
                        # Caso: Múltiples contactos (preguntar cuál)
                        elif len(contacts) > 1:
                            print_color("\n🔍 Varios contactos encontrados:", Colors.BLUE)
                            for i, contact in enumerate(contacts, 1):
                                print_color(f"  {i}. {contact.get('name')} - {contact.get('phone')}", Colors.BLUE)
                            selection = input("\nSelecciona un número (o 'cancelar'): ").strip()
                            if selection.isdigit() and 0 < int(selection) <= len(contacts):
                                selected = contacts[int(selection)-1]
                                message = extract_message_from_input(user_input) or input("Mensaje a enviar: ").strip()
                                send_response = requests.post(
                                    "http://localhost:5000/send-to-contact",
                                    json={
                                        "contact_name": selected.get('name'),
                                        "message": message
                                    }
                                )
                                if send_response.status_code == 200:
                                    print_color(f"\n✅ Mensaje enviado a {selected.get('name')}: {message}", Colors.GREEN)
                    
                    # Caso: Otros tipos de output (diccionario)
                    elif isinstance(response['output'], dict):
                        print_tool_response(response['tool_name'], response['output'])
                
                # Si no hay output pero hay respuesta del asistente (ej: saludos)
                elif response.get('response'):
                    print_color(f"\n🤖 Asistente: {response['response']}", Colors.GREEN)

        except KeyboardInterrupt:
            print_color("\n🛑 Saliendo del chat...", Colors.BLUE)
            break
        except Exception as e:
            print_color(f"\n⚠️ Error inesperado: {str(e)}", Colors.RED)

def extract_message_from_input(user_input):
    """
    Extrae el mensaje de frases como:
    - "envía [mensaje] a [contacto]"
    - "di a [contacto] que [mensaje]"
    - "manda [mensaje] a [contacto]"
    - "envia un mensaje a [contacto] diciendo [mensaje]"
    """
    # Patrones comunes (con expresiones regulares mejoradas)
    patterns = [
        r"(?:envía|envia|manda|di)\s+(?:un mensaje|un msj|mensaje|msj)?\s*a\s*\w+\s*(?:que diga|diciendo|que|con el mensaje)?\s*(.*)",  # Caso 1
        r"(?:di|decile)\s+a\s*\w+\s*que\s*(.*)",  # Caso 2
        r"(?:manda|envía)\s+(?:el mensaje|la nota)?\s*['\"](.*)['\"]\s*a\s*\w+",  # Caso 3 (mensajes entre comillas)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
    
    return None
            
            
if __name__ == "__main__":
    chat()