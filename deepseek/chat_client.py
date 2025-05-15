import requests
import json
from uuid import uuid4

API_URL = "http://localhost:5000/mcp-to-deepseek"
SESSION_ID = str(uuid4())

def print_colored(text, color):
    """Funcion para imprimir en colores (opcional)"""
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'end': '\033[0m'
    }
    print(f"{colors.get(color, '')}{text}{colors['end']}")

def chat():
    print_colored("\nBienvenido al chat con DeepSeek", "blue")
    print_colored(f"Session ID: {SESSION_ID}", "yellow")
    print_colored("Escribe 'salir' para terminar\n", "green")
    
    while True:
        try:
            user_input = input("Tú: ")
            if user_input.lower() in ['salir', 'exit', 'quit']:
                print_colored("\n¡Hasta luego!", "blue")
                break

            payload = {
                "input": user_input,
                "session_id": SESSION_ID
            }

            response = requests.post(
                API_URL,
                headers={"Content-Type": "application/json"},
                json=payload
            )
            
            def print_tool_response(tool_name, output):
                """Imprime respuestas de herramientas con formato"""
                if tool_name == "sumar":
                    print(f"\n🔢 Resultado: {output.get('resultado', '?')}")
                elif tool_name == "buscar_repos":
                    print("\n📂 Repositorios encontrados:")
                    for repo in output:
                        print(f"\n  🏷️ {repo.get('name', 'Sin nombre')}")
                        print(f"  📝 {repo.get('description', 'Sin descripción')}")
                        print(f"  ⭐ {repo.get('stars', 'N/A')} estrellas")
                        print(f"  🔗 {repo.get('url', 'No disponible')}")
                else:
                    print(f"\n[Herramienta: {tool_name}]\n{json.dumps(output, indent=2)}")
                        
            if response.status_code == 200:
                data = response.json()
                print_colored(f"\nAsistente: {data['response']}", "green")
                if data.get('tool_used'):
                    print_colored(f"[Herramienta usada: {data['tool_name']}]", "yellow")
                    if data.get('output'):
                        print_colored(f"[Resultado: {json.dumps(data['output'], indent=2)}]", "yellow")
            else:
                print_colored(f"\nError {response.status_code}:", "red")
                print_colored(response.text, "red")

        except KeyboardInterrupt:
            print_colored("\nSaliendo del chat...", "blue")
            break
        except Exception as e:
            print_colored(f"\nError inesperado: {str(e)}", "red")

if __name__ == "__main__":
    chat()