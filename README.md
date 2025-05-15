## Consultas con CURL
    curl -X POST http://localhost:5000/send-to-contact \
    -H "Content-Type: application/json" \
    -d '{
    "contact_name": "Juan",
    "message": "Hola desde curl"
    }'
