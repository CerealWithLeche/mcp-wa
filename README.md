## Iniciar servidor WA
Clonar: https://github.com/lharries/whatsapp-mcp.git

En whatsapp-bridge/ iniciar el servidor con

    go run main.go
Escanear QR

## Interactuar directamente con asistente de terminal(DeepSeek o GPT)
1. Una vez iniciado el servidor de WA
3. Crear un nuervo entorno para
4. Satisfacer las dependencias de app.py y chat_client.py
5. Iniciar app.py

**Para interacción "natural"**

6. Iniciar chat_client.py

## Consultas con CURL
Es una forma más rápida que envíar prompts en chat_client.py
- Iniciar main.go y app.py
### Envíar mensaje a un contacto especifico
    curl -X POST http://localhost:5000/send-to-contact \
    -H "Content-Type: application/json" \
    -d '{
    "contact_name": "Juan",
    "message": "Hola desde curl"
    }'
#### Respuesta esperada
    {
      "success": true,
      "message": "Mensaje enviado a 5217771234567",
      "contact": {
        "jid": "5217771234567@s.whatsapp.net",
        "name": "Juan",
        "phone": "5217771234567"
      }
    }

### Buscar contactos
    curl -X POST http://localhost:5000/search-contacts \
      -H "Content-Type: application/json" \
      -d '{"query": "Juan"}'
#### Respuesta esperada
    {
      "success": true,
      "count": 1,
      "contacts": [
        {
          "name": "Juan",
          "jid": "5217771234567@s.whatsapp.net",
          "phone": "5217771234567"
        }
      ]
    }

### Iteractuar con el asistente (MCP-to-OpenAI)
    curl -X POST http://localhost:5000/mcp-to-openai \
      -H "Content-Type: application/json" \
      -d '{
        "input": "envía un mensaje a juan que diga hola",
        "session_id": "mi-sesion-unica"
      }'
#### Respuesta esperada
    {
      "response": "Mensaje enviado a juan",
      "session_id": "mi-sesion-unica",
      "tool_used": true,
      "tool_name": "send_message",
      "output": {
        "success": true,
        "message": "Mensaje enviado a 5217771234567",
        "recipient": "5215646404427@s.whatsapp.net"
      }
    }    

### Controlar servidor de WA
Iniciar servidor

    curl -X POST http://localhost:5000/control-whatsapp-server \
      -H "Content-Type: application/json" \
      -d '{"action": "start"}'

Detener servidor

    curl -X POST http://localhost:5000/control-whatsapp-server \
      -H "Content-Type: application/json" \
      -d '{"action": "stop"}'
