## Consultas con CURL
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
